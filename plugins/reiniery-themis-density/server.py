# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=2,<3"]
# ///
"""Read-only local density summaries; no raw-data publication."""
import csv
import math
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

from typing import Any
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

mcp = MCPServer("reiniery-themis-density")


def utc(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat().replace("+00:00", "Z")


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def load(spacecraft="THA", start=None, end=None, region="all"):
    if spacecraft not in {"THA", "THD", "THE"} or region not in {"all", "inside", "outside"}:
        raise ToolError("Choose spacecraft THA/THD/THE and region all/inside/outside.")
    setting = os.getenv("THEMIS_DATA_DIR", "").strip()
    folder = Path(setting) if setting else Path(__file__).parent / "data"
    paths = sorted(folder.glob(f"den-scpot-*-{spacecraft.lower()}-*.dat"))
    if not paths:
        raise ToolError("No spacecraft files found. Set THEMIS_DATA_DIR to the folder containing den-scpot-YYYYMMDD-tha-1.dat files; the synthetic demo only has THA.")
    rows=[]
    mismatches=0
    for path in paths:
        try:
            date=datetime.strptime(path.name.split("-")[2], "%Y%m%d").replace(tzinfo=timezone.utc).timestamp()
        except (ValueError, IndexError):
            continue
        # Include adjacent dates to avoid trusting filename boundaries for selection.
        if start is not None and (date+172800 < start or date-86400 >= end):
            continue
        try:
            for line in path.read_text().splitlines():
                f=line.split()
                if len(f)!=13:
                    raise ToolError("Expected 13 columns per row. Check dataset format.")
                t,d=number(f[0]),number(f[7])
                flag=f[8]
                if flag not in {"0","1"} or f[12]!={"THA":"1","THD":"4","THE":"5"}[spacecraft]:
                    raise ToolError("Unexpected plasmapause flag or spacecraft number. Check source data.")
                if t is None:
                    raise ToolError("Invalid Unix timestamp in source data.")
                calendar=datetime(*map(int,f[1:7]),tzinfo=timezone.utc).timestamp()
                mismatch=abs(t-calendar)>1
                if start is not None and not start<=t<end:
                    continue
                if region!="all" and flag!={"inside":"0","outside":"1"}[region]:
                    continue
                mismatches+=int(mismatch)
                rows.append((t,d,flag))
        except (OSError, ValueError, OverflowError):
            raise ToolError("Could not parse source file. Check readability and calendar fields.") from None
    source="local research DAT files" if setting else "SYNTHETIC DEMONSTRATION; not observations"
    return rows, source, mismatches


def interval(start_utc, end_utc):
    try:
        a, b = [datetime.fromisoformat(x.replace("Z", "+00:00")) for x in (start_utc, end_utc)]
        if a.tzinfo is None or b.tzinfo is None or a >= b:
            raise ValueError
        return a.timestamp(), b.timestamp()
    except (ValueError, TypeError, OverflowError):
        raise ToolError("Use ordered ISO-8601 times with timezone, e.g. 2008-06-01T00:00:00Z and 2008-06-02T00:00:00Z.") from None


@mcp.tool()
def describe_dataset(spacecraft: str = "THA") -> dict[str, Any]:
    """Inspect local 13-column THEMIS DAT files for THA, THD or THE. Return coverage, cadence, plasmapause flags (0 inside, 1 outside) and timestamp consistency. No setting uses synthetic THA data."""
    rows,source,mismatches=load(spacecraft)
    times=sorted(t for t,_,_ in rows); unique=sorted(set(times))
    return {"source":source,"spacecraft":spacecraft,"density_units":"cm^-3",
            "records":len(rows),"first_utc":utc(times[0]) if times else None,
            "last_utc":utc(times[-1]) if times else None,
            "median_spacing_seconds":median([y-x for x,y in zip(unique,unique[1:])]) if len(unique)>1 else None,
            "plasmapause_flag_counts":dict(Counter(q for _,_,q in rows)),
            "calendar_timestamp_mismatches":mismatches,
            "time_note":"Queries use column 1 as Unix UTC; calendar-column mismatches require review.",
            "coordinates":"L, MLT (hours), MLAT (degrees); no spatial filtering applied."}


@mcp.tool()
def summarize_density(start_utc: str, end_utc: str, spacecraft: str = "THA", region: str = "all") -> dict[str, Any]:
    """Summarize density (cm^-3) in [start,end), e.g. 2008-06-01T00:00:00Z to 2008-06-02T00:00:00Z. Choose THA/THD/THE and region all/inside/outside the plasmapause. Finite positive values only; sample-weighted, not interpolated. Flag is a region label, not quality."""
    a,b=interval(start_utc,end_utc); rows,source,mismatches=load(spacecraft,a,b,region)
    good=[(t,d) for t,d,_ in rows if d is not None and d>0]; values=[d for _,d in good]
    peak=max(good,key=lambda x:x[1]) if good else None
    return {"source":source,"spacecraft":spacecraft,"region":region,"density_units":"cm^-3",
            "start_utc":utc(a),"end_utc_exclusive":utc(b),"records":len(rows),
            "valid_positive_density_records":len(good),"excluded_density_records":len(rows)-len(good),
            "mean":mean(values) if good else None,"median":median(values) if good else None,
            "minimum":min(values) if good else None,"maximum":peak[1] if peak else None,
            "peak_utc":utc(peak[0]) if peak else None,
            "plasmapause_flag_counts":dict(Counter(q for _,_,q in rows)),
            "calendar_timestamp_mismatches":mismatches,
            "note":"Column 1 Unix UTC; sample-weighted. No records means no data, not zero density."}


@mcp.tool()
def find_sampling_gaps(start_utc: str, end_utc: str, spacecraft: str = "THA", expected_cadence_seconds: float = 300.0, tolerance: float = 1.5) -> dict[str, Any]:
    """Find sampling gaps for one spacecraft THA/THD/THE in [start,end), including edges. Use ISO-8601 timezone dates. Defaults: 300-second cadence, 1.5 tolerance; gap exceeds 450 seconds. Uses all regions and all density values. Return largest 10 gaps and totals, not a diagnosis of instrument downtime."""
    a,b=interval(start_utc,end_utc)
    if not math.isfinite(expected_cadence_seconds) or expected_cadence_seconds<=0 or not math.isfinite(tolerance) or tolerance<1:
        raise ToolError("Choose finite positive cadence seconds and tolerance >= 1.")
    rows,source,mismatches=load(spacecraft,a,b)
    times=sorted(set(t for t,_,_ in rows)); threshold=expected_cadence_seconds*tolerance
    spans=[(a,b,"no_records")] if not times else [(a,times[0],"leading_edge")]+[(x,y,"internal") for x,y in zip(times,times[1:])]+[(times[-1],b,"trailing_edge")]
    gaps=[{"start_utc":utc(x),"end_utc":utc(y),"elapsed_seconds":y-x,"kind":kind} for x,y,kind in spans if y-x>threshold or kind=="no_records"]
    return {"source":source,"spacecraft":spacecraft,"unique_timestamps":len(times),
            "threshold_seconds":threshold,"gap_count":len(gaps),
            "total_gap_span_seconds":sum(g["elapsed_seconds"] for g in gaps),
            "largest_gaps":sorted(gaps,key=lambda g:g["elapsed_seconds"],reverse=True)[:10],
            "calendar_timestamp_mismatches":mismatches,
            "note":"All regions; span durations are not exact downtime. Queries use column 1 Unix UTC. Dataset selection can itself cause gaps."}


if __name__ == "__main__":
    mcp.run(transport="stdio")
