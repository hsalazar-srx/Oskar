"""
OSKAR — src.services.bom package.

Re-exports every public name so callers import from src.services.bom rather
than reaching into individual submodules, matching the src/services/ecn
package convention.
"""

from src.services.bom.models import (
    BOMCycleError,
    BOMHead,
    BOMLine,
    BOMTreeNode,
    WhereUsedLine,
)
from src.services.bom.browse import get_single_level_bom
from src.services.bom.explode import assemble_where_used, build_bom_tree, rollup_quantities
from src.services.bom.mpn_master import (
    ItemMPN,
    MpnSearchHit,
    MpnSearchResult,
    NormalizeResult,
    get_item_mpn,
    is_current_default,
    load_synonyms,
    normalize_manufacturer,
    search_item_mpns,
    upsert_item_mpn,
    wildcard_to_like,
)
from src.services.bom.zecnmpms_transform import (
    DefaultFlagViolation,
    DuplicateCollapse,
    TransformBatchResult,
    TransformedRow,
    natural_key,
    transform_batch,
    transform_row,
)

__all__ = [
    "BOMCycleError",
    "BOMHead",
    "BOMLine",
    "BOMTreeNode",
    "WhereUsedLine",
    "get_single_level_bom",
    "assemble_where_used",
    "build_bom_tree",
    "rollup_quantities",
    "ItemMPN",
    "MpnSearchHit",
    "MpnSearchResult",
    "NormalizeResult",
    "get_item_mpn",
    "is_current_default",
    "load_synonyms",
    "normalize_manufacturer",
    "search_item_mpns",
    "upsert_item_mpn",
    "wildcard_to_like",
    "DefaultFlagViolation",
    "DuplicateCollapse",
    "TransformBatchResult",
    "TransformedRow",
    "natural_key",
    "transform_batch",
    "transform_row",
]
