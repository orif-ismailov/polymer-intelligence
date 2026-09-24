"""The closed vocabularies of the technologist marketplace.

Expertise is a CLOSED set rather than free text because a factory's request is
matched against it: «экструзия», «Extrusion» and «экструдер» typed by three
experts are three values no filter can join. Equipment brands stay free — there
are hundreds, and nothing is matched on them yet.

Stored as `text`/`text[]` with a CHECK or a Python-side validation rather than
as PG ENUMs, so adding «thermoforming» is a code change and not a migration —
the same call `logistics_requests.volume_unit` makes.

The portal renders every label from its own locale file keyed on these values
(`technologists.<set>.<value>`); the API only ever speaks the keys.
"""

from __future__ import annotations

from typing import Literal, get_args

Industry = Literal["petrochemical", "polymer", "packaging", "automotive", "recycling", "chemical"]
Process = Literal[
    "extrusion",
    "injection_molding",
    "blow_molding",
    "compounding",
    "film",
    "pipe",
    "recycling",
    "thermoforming",
]
Material = Literal["PE", "HDPE", "LDPE", "LLDPE", "PP", "PVC", "PET", "PS", "ABS", "PA", "PC", "EVA"]
NeedType = Literal[
    "equipment_setup",
    "material_selection",
    "production_launch",
    "troubleshooting",
    "process_optimization",
    "other",
]
Urgency = Literal["urgent", "week", "month", "date"]
#: What a factory asks for — `both` means «either suits us».
RequestFormat = Literal["online", "on_site", "both"]
#: What an expert offers — a list, so «both» is just the two values.
ProfileFormat = Literal["online", "on_site"]
CapacityUnit = Literal["kg_h", "t_day", "t_month"]
Currency = Literal["USD", "UZS", "EUR"]
#: ISO 639-1. Closed so a filter by language is a filter and not a guess.
Language = Literal["ru", "uz", "en", "zh", "tr", "de", "fa", "kk"]

INDUSTRIES: tuple[str, ...] = get_args(Industry)
PROCESSES: tuple[str, ...] = get_args(Process)
MATERIALS: tuple[str, ...] = get_args(Material)
NEED_TYPES: tuple[str, ...] = get_args(NeedType)
URGENCIES: tuple[str, ...] = get_args(Urgency)
REQUEST_FORMATS: tuple[str, ...] = get_args(RequestFormat)
PROFILE_FORMATS: tuple[str, ...] = get_args(ProfileFormat)
CAPACITY_UNITS: tuple[str, ...] = get_args(CapacityUnit)
CURRENCIES: tuple[str, ...] = get_args(Currency)
LANGUAGES: tuple[str, ...] = get_args(Language)


def facets() -> dict[str, list[str]]:
    """Every closed set, for the portal's filters and editors — one source."""
    return {
        "industries": list(INDUSTRIES),
        "processes": list(PROCESSES),
        "materials": list(MATERIALS),
        "need_types": list(NEED_TYPES),
        "urgencies": list(URGENCIES),
        "request_formats": list(REQUEST_FORMATS),
        "profile_formats": list(PROFILE_FORMATS),
        "capacity_units": list(CAPACITY_UNITS),
        "currencies": list(CURRENCIES),
        "languages": list(LANGUAGES),
    }
