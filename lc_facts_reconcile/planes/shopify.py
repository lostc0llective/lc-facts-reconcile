"""Plane 3 — live Shopify metafields.

Uses paginated Admin GraphQL reads. Requires:
  SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET  (minted via client_credentials)
  SHOPIFY_STORE                               (defaults to lost-collective.myshopify.com)

Run via: op run --env-file=~/Claude/code-projects/lost-collective-dawn/.env.tpl -- lc-facts-reconcile
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from ..diff import PlaneData

logger = logging.getLogger(__name__)

DEFAULT_STORE = "lost-collective.myshopify.com"
API_VERSION = "2024-01"

_cached_token: dict[str, Any] = {}


def get_store() -> str:
    return os.environ.get("SHOPIFY_STORE", DEFAULT_STORE)


def get_admin_token() -> str:
    """Mint a fresh Shopify Admin API token via client_credentials. Cached per process."""
    if _cached_token.get("token") and time.time() < _cached_token.get("expires_at", 0):
        return _cached_token["token"]

    client_id = os.environ.get("SHOPIFY_CLIENT_ID", "").strip()
    client_secret = os.environ.get("SHOPIFY_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise RuntimeError(
            "SHOPIFY_CLIENT_ID / SHOPIFY_CLIENT_SECRET not set.\n"
            "Run via: op run --env-file=~/Claude/code-projects/lost-collective-dawn/.env.tpl -- lc-facts-reconcile"
        )

    store = get_store()
    url = f"https://{store}/admin/oauth/access_token"
    payload = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
    }).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())

    token = data.get("access_token", "")
    expires_in = int(data.get("expires_in", 86399))
    if not token:
        raise RuntimeError(f"No access_token in Shopify response: {data}")

    _cached_token["token"] = token
    _cached_token["expires_at"] = time.time() + expires_in - 60
    return token


def gql(query: str, variables: dict | None = None) -> dict:
    token = get_admin_token()
    store = get_store()
    url = f"https://{store}/admin/api/{API_VERSION}/graphql.json"
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": token,
        },
        method="POST",
    )
    logger.debug("Shopify GQL request: query=%s variables=%s", query.split("\n", 2)[1].strip() if "\n" in query else query[:80], variables)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Shopify GQL HTTP {e.code}: {e.reason}") from e

    logger.debug("Shopify GQL response: data_keys=%s errors=%s", list((data.get("data") or {}).keys()), data.get("errors"))

    if data.get("errors"):
        # Field-level GraphQL errors land here, not in HTTPError. Surface loud
        # so the silent-failure mode that masked the 2026-05-31 PRODUCTS_QUERY
        # bug never recurs.
        raise RuntimeError(f"Shopify GQL errors: {data['errors']}")

    return data


COLLECTION_QUERY = """
query CollectionByHandle($handle: String!) {
  collectionByHandle(handle: $handle) {
    id
    title
    description
    seo { title description }
  }
}
"""

METAOBJECT_QUERY = """
query MetaobjectByHandle($handle: String!) {
  metaobjectByHandle(handle: {type: "series", handle: $handle}) {
    fields {
      key
      value
    }
  }
}
"""

PRODUCTS_QUERY = """
query ProductsInCollection($handle: String!, $after: String) {
  collectionByHandle(handle: $handle) {
    products(first: 50, after: $after) {
      edges {
        cursor
        node {
          id
          title
          handle
          bodyHtml
          seo { title description }
          mf_print_story: metafield(namespace: "custom", key: "print_story") { value }
          mf_subject_description: metafield(namespace: "custom", key: "subject_description") { value }
          mf_capture_date: metafield(namespace: "custom", key: "capture_date") { value }
          mf_year_photographed: metafield(namespace: "custom", key: "year_photographed") { value }
          mf_origin_line: metafield(namespace: "custom", key: "origin_line") { value }
          mf_camera_body: metafield(namespace: "custom", key: "camera_body") { value }
          mf_lens: metafield(namespace: "custom", key: "lens") { value }
          images(first: 5) {
            edges {
              node {
                altText
                src
              }
            }
          }
        }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

_PRODUCT_METAFIELD_ALIASES = {
    "mf_print_story": "print_story",
    "mf_subject_description": "subject_description",
    "mf_capture_date": "capture_date",
    "mf_year_photographed": "year_photographed",
    "mf_origin_line": "origin_line",
    "mf_camera_body": "camera_body",
    "mf_lens": "lens",
}


@dataclass
class ShopifyReadResult:
    handle: str
    plane: PlaneData
    product_count: int
    error: str | None = None


def read_shopify(handle: str) -> ShopifyReadResult:
    """Read live Shopify data for a series handle and return a PlaneData."""
    logger.debug("read_shopify(handle=%s) starting", handle)
    plane = PlaneData()

    try:
        _read_collection(handle, plane)
        _read_metaobject(handle, plane)
        product_count = _read_products(handle, plane)
    except Exception as exc:
        logger.debug("read_shopify(handle=%s) error: %s", handle, exc)
        return ShopifyReadResult(handle=handle, plane=plane, product_count=0, error=str(exc))

    logger.debug("read_shopify(handle=%s) finished — %d products / %d values", handle, product_count, len(plane.values))
    return ShopifyReadResult(handle=handle, plane=plane, product_count=product_count)


def _read_collection(handle: str, plane: PlaneData) -> None:
    resp = gql(COLLECTION_QUERY, {"handle": handle})
    coll = (resp.get("data") or {}).get("collectionByHandle")
    if not coll:
        return

    if coll.get("description"):
        plane.values[("collection.description", "description")] = coll["description"]
    seo = coll.get("seo") or {}
    if seo.get("title"):
        plane.values[("collection.seo", "title")] = seo["title"]
    if seo.get("description"):
        plane.values[("collection.seo", "description")] = seo["description"]


def _read_metaobject(handle: str, plane: PlaneData) -> None:
    resp = gql(METAOBJECT_QUERY, {"handle": handle})
    obj = (resp.get("data") or {}).get("metaobjectByHandle")
    if not obj:
        return
    for f in obj.get("fields") or []:
        key = f.get("key")
        val = f.get("value")
        if key and val:
            plane.values[("series.metaobject", key)] = val


def _read_products(handle: str, plane: PlaneData) -> int:
    count = 0
    cursor = None

    while True:
        variables: dict = {"handle": handle}
        if cursor:
            variables["after"] = cursor

        resp = gql(PRODUCTS_QUERY, variables)
        products_conn = (
            (resp.get("data") or {})
            .get("collectionByHandle") or {}
        ).get("products") or {}

        edges = products_conn.get("edges") or []
        for edge in edges:
            node = edge.get("node") or {}
            ph = node.get("handle", "")
            if not ph:
                continue
            count += 1

            if node.get("bodyHtml"):
                plane.values[(f"product.{ph}", "body_html")] = node["bodyHtml"]
            seo = node.get("seo") or {}
            if seo.get("description"):
                plane.values[(f"product.{ph}", "seo.description")] = seo["description"]

            for alias, key in _PRODUCT_METAFIELD_ALIASES.items():
                mf = node.get(alias)
                if mf and mf.get("value"):
                    plane.values[(f"product.{ph}", key)] = mf["value"]

            for img_edge in (node.get("images") or {}).get("edges") or []:
                img = img_edge.get("node") or {}
                if img.get("altText"):
                    src_stem = img.get("src", "").split("/")[-1].split("?")[0]
                    plane.values[(f"product.{ph}", f"alt_text.{src_stem}")] = img["altText"]

        page_info = products_conn.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        if not cursor:
            break

    return count
