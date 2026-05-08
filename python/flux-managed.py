#!/usr/bin/env python3
"""
Find Kubernetes resources not managed by Flux (directly or transitively).

A resource is considered managed if it carries Flux labels, or if its owner
chain leads to a resource that does.  Only the topmost unmanaged resource in
any owner chain is reported — children of an unmanaged resource are suppressed.

Additional inference strategies (beyond ownerReferences):

  CRD-based inference (--infer-from-crd, on by default):
    If a resource's CustomResourceDefinition has Flux labels, the resource is
    treated as managed.  This handles operator-created CRD instances that carry
    no ownerRef (e.g. Longhorn Settings/Nodes/Volumes managed internally by the
    Longhorn operator whose CRDs were installed by Flux).

  StatefulSet PVC inference (always on):
    PVCs from StatefulSet volumeClaimTemplates may not have ownerReferences on
    older clusters (pre-1.27).  The naming convention
    <templateName>-<statefulSetName>-<ordinal> is used to infer ownership.

  Managed namespaces (--managed-namespace NS):
    All resources in listed namespaces are treated as managed.  Use this for
    operator-created resources that have no ownerRef and whose kind is a core
    Kubernetes type (e.g. ConfigMaps written by the Datadog agent) where neither
    ownerRef nor CRD inference can help.

  System-managed resources (always skipped):
    - ConfigMaps named kube-root-ca.crt  (created by kube-controller-manager)
    - Secrets with label owner=helm or name prefix sh.helm.release.v1.
      (Helm release state, managed by Helm itself)

Usage:
    python3 flux-managed.py [flags]

Requirements:
    pip install kubernetes
"""

import argparse
import json
import re
import sys
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

try:
    from kubernetes import client as k8s, config
    from kubernetes.dynamic import DynamicClient
except ImportError:
    print(
        "Error: kubernetes package not installed.  Run: pip install kubernetes",
        file=sys.stderr,
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FLUX_LABELS: FrozenSet[str] = frozenset(
    {
        "kustomize.toolkit.fluxcd.io/name",
        "helm.toolkit.fluxcd.io/name",
    }
)

# Excluded by default: informational / auto-generated / always-noisy kinds.
DEFAULT_EXCLUDE_KINDS: FrozenSet[str] = frozenset(
    {
        "Event",
        "EndpointSlice",
        "Lease",
        "Endpoints",
        "ComponentStatus",
    }
)

PAGE_SIZE = 500

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Find Kubernetes resources not managed by Flux.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--kubeconfig", metavar="PATH", help="Path to kubeconfig file")
    p.add_argument("--context", metavar="NAME", help="Kubeconfig context")
    p.add_argument("--namespace", "-n", metavar="NS", help="Limit to a single namespace")
    p.add_argument(
        "--exclude-namespace",
        "-N",
        action="append",
        default=[],
        dest="exclude_namespaces",
        metavar="NS",
        help="Exclude a namespace (repeatable)",
    )
    p.add_argument(
        "--managed-namespace",
        "-M",
        action="append",
        default=[],
        dest="managed_namespaces",
        metavar="NS",
        help=(
            "Treat all resources in this namespace as Flux-managed (repeatable). "
            "Use for namespaces containing operator-created resources with no "
            "ownerRef and no CRD (e.g. ConfigMaps written by the Datadog agent)."
        ),
    )
    p.add_argument(
        "--skip-terminating",
        action="store_true",
        help="Skip resources that have deletionTimestamp set",
    )
    p.add_argument(
        "--skip-failed-pods",
        action="store_true",
        help="Skip Pods in Succeeded or Failed phase",
    )
    p.add_argument(
        "--include-types",
        action="append",
        default=[],
        dest="include_types",
        metavar="KIND",
        help="Only check these kinds (repeatable); all others are skipped",
    )
    p.add_argument(
        "--exclude-types",
        action="append",
        default=[],
        dest="exclude_types",
        metavar="KIND",
        help="Additional kinds to exclude on top of the built-in list (repeatable)",
    )
    p.add_argument(
        "--no-infer-from-crd",
        action="store_false",
        dest="infer_from_crd",
        default=True,
        help=(
            "Disable CRD-based inference. By default, CRD instances are treated "
            "as managed when their CRD carries Flux labels."
        ),
    )
    p.add_argument("--json", action="store_true", dest="output_json", help="Output as JSON array")
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show full owner chain for each reported resource",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Kubernetes client
# ---------------------------------------------------------------------------


def load_kube_client(args: argparse.Namespace) -> k8s.ApiClient:
    try:
        if args.kubeconfig or args.context:
            config.load_kube_config(
                config_file=args.kubeconfig or None,
                context=args.context or None,
            )
        else:
            try:
                config.load_incluster_config()
            except config.ConfigException:
                config.load_kube_config()
    except Exception as exc:
        print(f"Error loading kubeconfig: {exc}", file=sys.stderr)
        sys.exit(1)
    return k8s.ApiClient()


# ---------------------------------------------------------------------------
# Resource-type discovery
# ---------------------------------------------------------------------------


def _collect_types(resources_raw, api_version: str, out: list) -> None:
    """Append listable, non-subresource types from a raw resource list."""
    group = api_version.split("/")[0] if "/" in api_version else ""

    for r in resources_raw:
        if isinstance(r, dict):
            name = r.get("name", "")
            kind = r.get("kind", "")
            namespaced = r.get("namespaced", True)
            verbs = r.get("verbs", []) or []
        else:
            name = getattr(r, "name", "") or ""
            kind = getattr(r, "kind", "") or ""
            namespaced = getattr(r, "namespaced", True)
            verbs = list(getattr(r, "verbs", []) or [])

        if "/" in name or not kind:
            continue  # skip subresources
        if "list" not in verbs:
            continue

        out.append(
            {
                "api_version": api_version,
                "kind": kind,
                "namespaced": namespaced,
                "plural": name,   # e.g. "settings"
                "group": group,   # e.g. "longhorn.io"
            }
        )


def discover_resource_types(api_client: k8s.ApiClient) -> List[dict]:
    """Return all listable resource types across every API group."""
    results: list = []

    # Core v1
    try:
        core = k8s.CoreV1Api(api_client)
        _collect_types(core.get_api_resources().resources, "v1", results)
    except Exception as exc:
        print(f"Warning: core v1 discovery failed: {exc}", file=sys.stderr)

    # Named API groups (preferred version only)
    try:
        groups = k8s.ApisApi(api_client).get_api_versions().groups
    except Exception as exc:
        print(f"Warning: API group discovery failed: {exc}", file=sys.stderr)
        groups = []

    for group in groups:
        gv = group.preferred_version.group_version
        try:
            data = api_client.call_api(
                f"/apis/{gv}",
                "GET",
                {},
                [],
                {"Accept": "application/json"},
                body=None,
                post_params=[],
                files={},
                response_type="object",
                auth_settings=["BearerToken"],
                _return_http_data_only=True,
                _preload_content=True,
            )
            _collect_types(data.get("resources", []), gv, results)
        except Exception:
            pass

    # Deduplicate by (api_version, kind)
    seen: set = set()
    deduped: list = []
    for rt in results:
        key = (rt["api_version"], rt["kind"])
        if key not in seen:
            seen.add(key)
            deduped.append(rt)
    return deduped


def build_crd_name_map(resource_types: List[dict]) -> Dict[Tuple[str, str], str]:
    """
    Build (api_version, kind) -> CRD name mapping.

    CRD names follow the convention <plural>.<group>, e.g.:
      ('longhorn.io/v1beta2', 'Setting') -> 'settings.longhorn.io'
    Core (v1) resources have no group and therefore no CRD.
    """
    mapping: Dict[Tuple[str, str], str] = {}
    for rt in resource_types:
        group = rt.get("group", "")
        plural = rt.get("plural", "")
        if group and plural:
            crd_name = f"{plural}.{group}"
            mapping[(rt["api_version"], rt["kind"])] = crd_name
    return mapping


# ---------------------------------------------------------------------------
# Resource parsing
# ---------------------------------------------------------------------------


def _meta_get(meta, *attrs, default=None):
    """Attribute-then-dict lookup for metadata fields."""
    for attr in attrs:
        v = getattr(meta, attr, None)
        if v is not None:
            return v
        if isinstance(meta, dict):
            v = meta.get(attr)
            if v is not None:
                return v
    return default


def parse_resource(obj, kind: str, api_version: str) -> Optional[dict]:
    """Convert a dynamic-client object into our internal resource dict."""
    try:
        meta = getattr(obj, "metadata", None) or obj.get("metadata", {})
    except Exception:
        return None

    uid = _meta_get(meta, "uid", default="")
    if not uid:
        return None

    name = _meta_get(meta, "name", default="") or ""
    namespace = _meta_get(meta, "namespace", default="") or ""
    deletion_ts = _meta_get(meta, "deletion_timestamp", "deletionTimestamp")

    labels = _meta_get(meta, "labels", default={}) or {}
    if not isinstance(labels, dict):
        try:
            labels = dict(labels)
        except Exception:
            labels = {}

    owner_refs_raw = (
        _meta_get(meta, "owner_references", "ownerReferences", default=[]) or []
    )
    owner_refs: list = []
    for ref in owner_refs_raw:
        if isinstance(ref, dict):
            owner_refs.append(
                {
                    "uid": ref.get("uid", ""),
                    "kind": ref.get("kind", ""),
                    "name": ref.get("name", ""),
                    "api_version": ref.get("apiVersion", ""),
                    "controller": ref.get("controller", False) or False,
                }
            )
        else:
            owner_refs.append(
                {
                    "uid": getattr(ref, "uid", "") or "",
                    "kind": getattr(ref, "kind", "") or "",
                    "name": getattr(ref, "name", "") or "",
                    "api_version": getattr(ref, "api_version", "") or "",
                    "controller": getattr(ref, "controller", False) or False,
                }
            )

    # Pod phase (used by --skip-failed-pods)
    phase: Optional[str] = None
    if kind == "Pod":
        try:
            status = getattr(obj, "status", None) or obj.get("status", {})
            phase = _meta_get(status, "phase")
        except Exception:
            pass

    return {
        "uid": uid,
        "name": name,
        "namespace": namespace,
        "kind": kind,
        "api_version": api_version,
        "labels": labels,
        "owner_refs": owner_refs,
        "deletion_ts": deletion_ts,
        "phase": phase,
    }


# ---------------------------------------------------------------------------
# Resource loading
# ---------------------------------------------------------------------------


def _is_system_managed(res: dict) -> bool:
    """
    Return True for resources that are auto-created by Kubernetes or Helm
    and carry no meaningful management chain.
    """
    kind = res["kind"]
    name = res["name"]
    labels = res.get("labels", {}) or {}

    # ConfigMaps injected into every namespace by kube-controller-manager
    if kind == "ConfigMap" and name == "kube-root-ca.crt":
        return True

    # ServiceAccount "default" is auto-created in every namespace by the
    # service account controller and carries no ownerRef or Flux labels.
    if kind == "ServiceAccount" and name == "default":
        return True

    # Helm release history secrets (created/owned by Helm itself)
    if kind == "Secret":
        if name.startswith("sh.helm.release.v1."):
            return True
        if labels.get("owner") == "helm":
            return True

    return False


def _list_items(res_api, namespace: Optional[str]) -> list:
    """List all items for a resource type, handling API-server pagination."""
    items: list = []
    continue_token: Optional[str] = None

    while True:
        kwargs: dict = {"limit": PAGE_SIZE}
        if continue_token:
            kwargs["_continue"] = continue_token
        if namespace is not None:
            kwargs["namespace"] = namespace

        try:
            response = res_api.get(**kwargs)
        except Exception:
            break

        items.extend(getattr(response, "items", None) or [])

        # "continue" is a Python keyword — use getattr with a string.
        continue_token = None
        try:
            meta = getattr(response, "metadata", None)
            if meta is not None:
                continue_token = getattr(meta, "continue", None) or None
        except Exception:
            pass

        if not continue_token:
            break

    return items


def load_all_resources(
    dyn_client: DynamicClient,
    resource_types: List[dict],
    args: argparse.Namespace,
    cache: Dict[str, bool],
) -> Dict[str, dict]:
    """
    Fetch all resources and return uid → resource dict.

    System-managed resources are pre-seeded into cache as True so
    is_flux_managed() short-circuits for them without extra logic.
    """
    exclude_kinds = DEFAULT_EXCLUDE_KINDS | frozenset(args.exclude_types)
    include_kinds = frozenset(args.include_types)
    exclude_namespaces = frozenset(args.exclude_namespaces)
    managed_namespaces = frozenset(args.managed_namespaces)

    uid_to_resource: Dict[str, dict] = {}
    total = len(resource_types)

    for i, rt in enumerate(resource_types, 1):
        kind = rt["kind"]
        api_version = rt["api_version"]

        if include_kinds and kind not in include_kinds:
            continue
        if kind in exclude_kinds:
            continue

        print(
            f"\r  [{i}/{total}] {api_version}/{kind}{' ' * 30}",
            end="",
            file=sys.stderr,
        )

        try:
            res_api = dyn_client.resources.get(kind=kind, api_version=api_version)
        except Exception:
            continue

        namespace = args.namespace if (rt["namespaced"] and args.namespace) else None
        try:
            items = _list_items(res_api, namespace)
        except Exception:
            continue

        for obj in items:
            res = parse_resource(obj, kind, api_version)
            if res is None:
                continue

            ns = res["namespace"]
            if ns and ns in exclude_namespaces:
                continue
            if args.skip_terminating and res["deletion_ts"]:
                continue
            if (
                args.skip_failed_pods
                and kind == "Pod"
                and res["phase"] in ("Succeeded", "Failed")
            ):
                continue

            uid = res["uid"]
            uid_to_resource[uid] = res

            # Pre-seed cache for resources we know are always system-managed
            # or in user-declared managed namespaces.
            if _is_system_managed(res) or (ns and ns in managed_namespaces):
                cache[uid] = True

    print(
        f"\r  Loaded {len(uid_to_resource)} resources.{' ' * 50}",
        file=sys.stderr,
    )
    return uid_to_resource


# ---------------------------------------------------------------------------
# CRD-based inference
# ---------------------------------------------------------------------------


def build_flux_managed_crds(uid_to_resource: Dict[str, dict]) -> Set[str]:
    """
    Return the set of CRD names that directly carry Flux labels.

    If a CRD is Flux-managed (installed by a HelmRelease or Kustomization),
    all instances of that CRD can be considered transitively managed even when
    the operator creates them without ownerReferences.

    Example: Longhorn installs settings.longhorn.io, volumes.longhorn.io, etc.
    via its HelmRelease.  The CRDs have helm.toolkit.fluxcd.io/name labels, so
    Setting/Volume/Node instances are treated as managed even though Longhorn
    creates them internally without ownerRefs.
    """
    managed: Set[str] = set()
    for res in uid_to_resource.values():
        if res["kind"] != "CustomResourceDefinition":
            continue
        labels = res.get("labels", {}) or {}
        if FLUX_LABELS & labels.keys():
            managed.add(res["name"])  # e.g. "settings.longhorn.io"
    return managed


# ---------------------------------------------------------------------------
# StatefulSet PVC inference
# ---------------------------------------------------------------------------

_STS_ORDINAL_RE = re.compile(r"-(\d+)$")


def _find_statefulset_for_pvc(
    pvc_name: str,
    pvc_namespace: str,
    uid_to_resource: Dict[str, dict],
) -> Optional[str]:
    """
    Infer StatefulSet ownership of a PVC using the Kubernetes naming convention:
        <volumeClaimTemplateName>-<statefulSetName>-<ordinal>

    Because both the template name and the StatefulSet name can contain hyphens,
    we check every StatefulSet in the namespace and see if the PVC name ends with
    '-<stsName>-<ordinal>'.

    Returns the StatefulSet UID if found, None otherwise.
    """
    if not _STS_ORDINAL_RE.search(pvc_name):
        return None  # not a StatefulSet PVC (no trailing ordinal)

    for uid, res in uid_to_resource.items():
        if res["kind"] != "StatefulSet" or res["namespace"] != pvc_namespace:
            continue
        sts_name = res["name"]
        if re.search(rf"-{re.escape(sts_name)}-\d+$", pvc_name):
            return uid

    return None


# ---------------------------------------------------------------------------
# Flux-management detection
# ---------------------------------------------------------------------------


def _ctrl_ref(owner_refs: list) -> Optional[dict]:
    """Return the controlling ownerReference, or the first one if none is marked."""
    ctrl = next((r for r in owner_refs if r.get("controller")), None)
    return ctrl if ctrl is not None else (owner_refs[0] if owner_refs else None)


def _fetch_owner(
    owner_ref: dict,
    child_namespace: str,
    dyn_client: DynamicClient,
    uid_to_resource: Dict[str, dict],
) -> Optional[str]:
    """
    Attempt to fetch an owner that is not yet in uid_to_resource and add it.
    Returns the UID on success, None on failure.
    """
    kind = owner_ref.get("kind", "")
    api_version = owner_ref.get("api_version", "")
    name = owner_ref.get("name", "")
    uid = owner_ref.get("uid", "")

    if not (kind and name and uid):
        return None

    # Try the child's namespace first (most common), then cluster-scoped fallback.
    namespaces_to_try: List[Optional[str]] = []
    if child_namespace:
        namespaces_to_try.append(child_namespace)
    namespaces_to_try.append(None)

    for ns in namespaces_to_try:
        try:
            res_api = dyn_client.resources.get(kind=kind, api_version=api_version)
            obj = res_api.get(name=name, namespace=ns) if ns else res_api.get(name=name)
            res = parse_resource(obj, kind, api_version)
            if res and res["uid"]:
                uid_to_resource[res["uid"]] = res
                return res["uid"]
        except Exception:
            continue

    return None


def is_flux_managed(
    uid: str,
    uid_to_resource: Dict[str, dict],
    cache: Dict[str, bool],
    visiting: FrozenSet[str],
    dyn_client: DynamicClient,
    crd_name_map: Optional[Dict[Tuple[str, str], str]] = None,
    flux_managed_crds: Optional[Set[str]] = None,
) -> bool:
    """
    Recursively determine whether a resource is managed by Flux.

    Order of checks:
      1. Cache / cycle detection
      2. Direct Flux labels
      3. ownerReference chain (recursive)
      4. CRD-based inference (if crd_name_map and flux_managed_crds provided)
      5. StatefulSet PVC name-pattern inference (PersistentVolumeClaim only)
    """
    if uid in cache:
        return cache[uid]
    if uid in visiting:
        return True  # cycle → self-managed bootstrap Kustomization

    res = uid_to_resource.get(uid)
    if res is None:
        return False

    # Direct Flux label check (short-circuits before any owner walk)
    labels = res.get("labels", {}) or {}
    if FLUX_LABELS & labels.keys():
        cache[uid] = True
        return True

    visiting = visiting | {uid}

    # Walk the controlling owner reference
    ref = _ctrl_ref(res.get("owner_refs", []))
    if ref:
        owner_uid = ref["uid"]

        if owner_uid not in uid_to_resource:
            owner_uid = (
                _fetch_owner(ref, res.get("namespace", ""), dyn_client, uid_to_resource)
                or ""
            )

        if owner_uid:
            result = is_flux_managed(
                owner_uid, uid_to_resource, cache, visiting, dyn_client,
                crd_name_map, flux_managed_crds,
            )
            cache[uid] = result
            return result

    # No ownerRef (or owner not found) — try inference strategies.

    # CRD-based inference: if the CRD that defines this resource's kind carries
    # Flux labels, treat this instance as managed.
    if crd_name_map is not None and flux_managed_crds is not None:
        crd_key = (res["api_version"], res["kind"])
        crd_name = crd_name_map.get(crd_key)
        if crd_name and crd_name in flux_managed_crds:
            cache[uid] = True
            return True

    # StatefulSet PVC inference: match by naming convention when no ownerRef.
    if res["kind"] == "PersistentVolumeClaim":
        sts_uid = _find_statefulset_for_pvc(
            res["name"], res["namespace"], uid_to_resource
        )
        if sts_uid:
            result = is_flux_managed(
                sts_uid, uid_to_resource, cache, visiting, dyn_client,
                crd_name_map, flux_managed_crds,
            )
            if result:
                cache[uid] = True
                return True

    cache[uid] = False
    return False


# ---------------------------------------------------------------------------
# Finding root unmanaged resources
# ---------------------------------------------------------------------------


def find_reportable(
    uid_to_resource: Dict[str, dict],
    cache: Dict[str, bool],
    dyn_client: DynamicClient,
    crd_name_map: Optional[Dict[Tuple[str, str], str]] = None,
    flux_managed_crds: Optional[Set[str]] = None,
) -> List[Tuple[dict, str]]:
    """
    Return (resource, reason) for each resource that is:
      - Not Flux-managed (directly, by ownerRef chain, or by inference)
      - The topmost unmanaged node in its owner chain
        (its controlling parent is absent, Flux-managed, or a dangling ref)
    """
    reportable: List[Tuple[dict, str]] = []
    total = len(uid_to_resource)

    def managed(uid: str) -> bool:
        return is_flux_managed(
            uid, uid_to_resource, cache, frozenset(), dyn_client,
            crd_name_map, flux_managed_crds,
        )

    for i, (uid, res) in enumerate(list(uid_to_resource.items()), 1):
        print(f"\r  Analyzing {i}/{total}…{' ' * 20}", end="", file=sys.stderr)

        if managed(uid):
            continue

        ref = _ctrl_ref(res.get("owner_refs", []))

        if not ref:
            reportable.append((res, "no owner, no Flux labels"))
            continue

        owner_uid = ref["uid"]

        if owner_uid not in uid_to_resource:
            short_uid = owner_uid[:8] + "…" if len(owner_uid) > 8 else owner_uid
            reason = (
                f"owner {ref['kind']}/{ref['name']} (UID {short_uid}) not found in cluster"
            )
            reportable.append((res, reason))
            continue

        if managed(owner_uid):
            reason = (
                f"owner {ref['kind']}/{ref['name']} is Flux-managed "
                f"but resource carries no Flux labels"
            )
            reportable.append((res, reason))
        # else: parent is also unmanaged → suppress; parent will be reported

    print(f"\r  Analysis complete.{' ' * 40}", file=sys.stderr)
    return reportable


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _owner_chain(uid: str, uid_to_resource: Dict[str, dict]) -> List[str]:
    """Return [root, …, resource] as 'Kind/name' strings."""
    chain: List[str] = []
    visited: Set[str] = set()
    current = uid
    while current and current not in visited:
        visited.add(current)
        res = uid_to_resource.get(current)
        if not res:
            break
        chain.append(f"{res['kind']}/{res['name']}")
        ref = _ctrl_ref(res.get("owner_refs", []))
        if not ref:
            break
        current = ref["uid"]
    chain.reverse()
    return chain


def _sort_key(item: Tuple[dict, str]):
    res, _ = item
    return (res["namespace"] or "", res["kind"], res["name"])


def print_table(
    reportable: List[Tuple[dict, str]],
    uid_to_resource: Dict[str, dict],
    verbose: bool,
) -> None:
    if not reportable:
        print("\nAll resources are managed by Flux (or transitively managed).")
        return

    sorted_results = sorted(reportable, key=_sort_key)

    col_ns = max((len(r["namespace"] or "<cluster>") for r, _ in sorted_results), default=9)
    col_ns = max(col_ns, 9)
    col_kind = max((len(r["kind"]) for r, _ in sorted_results), default=4)
    col_kind = max(col_kind, 4)
    col_name = max((len(r["name"]) for r, _ in sorted_results), default=4)
    col_name = max(col_name, 4)

    header = f"{'NAMESPACE':<{col_ns}}  {'KIND':<{col_kind}}  {'NAME':<{col_name}}  REASON"
    sep = f"{'─' * col_ns}  {'─' * col_kind}  {'─' * col_name}  {'─' * 55}"

    print(f"\n{header}")
    print(sep)

    for res, reason in sorted_results:
        ns = res["namespace"] or "<cluster>"
        print(f"{ns:<{col_ns}}  {res['kind']:<{col_kind}}  {res['name']:<{col_name}}  {reason}")
        if verbose:
            chain = _owner_chain(res["uid"], uid_to_resource)
            if chain:
                print(f"  owner chain: {' → '.join(chain)}")

    print(f"\n{len(reportable)} unmanaged resource(s) found.", file=sys.stderr)


def print_json_output(
    reportable: List[Tuple[dict, str]],
    uid_to_resource: Dict[str, dict],
    verbose: bool,
) -> None:
    out = []
    for res, reason in sorted(reportable, key=_sort_key):
        entry: dict = {
            "namespace": res["namespace"] or None,
            "kind": res["kind"],
            "api_version": res["api_version"],
            "name": res["name"],
            "reason": reason,
        }
        if verbose:
            entry["owner_chain"] = _owner_chain(res["uid"], uid_to_resource)
        out.append(entry)
    print(json.dumps(out, indent=2))
    print(f"\n{len(reportable)} unmanaged resource(s) found.", file=sys.stderr)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    args = parse_args()

    print("Loading kubeconfig…", file=sys.stderr)
    api_client = load_kube_client(args)
    dyn_client = DynamicClient(api_client)

    print("Discovering resource types…", file=sys.stderr)
    resource_types = discover_resource_types(api_client)
    print(f"  Found {len(resource_types)} listable resource types.", file=sys.stderr)

    # Build (api_version, kind) -> CRD name map before fetching resources.
    crd_name_map = build_crd_name_map(resource_types) if args.infer_from_crd else None

    print("Fetching resources…", file=sys.stderr)
    cache: Dict[str, bool] = {}
    uid_to_resource = load_all_resources(dyn_client, resource_types, args, cache)

    # Determine which CRDs are directly Flux-managed (requires resources to be loaded).
    flux_managed_crds: Optional[Set[str]] = None
    if args.infer_from_crd:
        flux_managed_crds = build_flux_managed_crds(uid_to_resource)
        print(
            f"  CRD inference: {len(flux_managed_crds)} Flux-managed CRD(s) found.",
            file=sys.stderr,
        )

    print("Analyzing Flux management…", file=sys.stderr)
    reportable = find_reportable(
        uid_to_resource, cache, dyn_client, crd_name_map, flux_managed_crds
    )

    if args.output_json:
        print_json_output(reportable, uid_to_resource, args.verbose)
    else:
        print_table(reportable, uid_to_resource, args.verbose)

    sys.exit(1 if reportable else 0)


if __name__ == "__main__":
    main()
