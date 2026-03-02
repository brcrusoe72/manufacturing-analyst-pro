"""Static equipment knowledge base for web deployment.

Curated failure modes, root causes, and fixes for common food/packaging equipment.
Replaces live AgentSearch when running on Streamlit Cloud.
"""
from __future__ import annotations

EQUIPMENT_KB: dict[str, dict] = {
    "caser": {
        "name": "Case Packer / Caser",
        "failure_modes": [
            {
                "mode": "Discharge Rail Jam",
                "likely_cause": "Cases binding at the discharge rail transition point due to misalignment or product orientation issues. Common when cases are not square or flaps are not fully folded.",
                "root_causes": [
                    "Discharge rail guides worn or misaligned — gap allows cases to rotate and bind",
                    "Case glue not setting before discharge — flaps spring open and catch on rail edges",
                    "Line speed exceeding case former's ability to square cases consistently",
                ],
                "fixes": [
                    "Measure and re-shim discharge rail guides to spec (typically 1/8\" clearance per side)",
                    "Check hot melt temperature and application pattern — verify adhesive is bonding before discharge",
                    "Reduce line speed by 5-10% during peak jam periods and measure if jam rate drops proportionally",
                ],
                "pm_additions": [
                    "Weekly: inspect discharge rail wear strips, replace if groove depth > 1mm",
                    "Daily: verify hot melt temp at startup (should be within 5°F of spec)",
                    "Monthly: check rail alignment with straightedge across full length",
                ],
            },
            {
                "mode": "Tipped Product",
                "likely_cause": "Cans or containers tipping at the caser infeed, typically caused by conveyor-to-caser speed mismatch or worn guide rails that allow product to rotate.",
                "root_causes": [
                    "Infeed conveyor speed not synchronized with caser cycle — product arrives too fast and tips at transition",
                    "Guide rail height or width out of spec for current container size — product wobbles at speed",
                    "Accumulation table pressure too high pushing product into caser infeed at an angle",
                ],
                "fixes": [
                    "Verify infeed conveyor speed matches caser cycle rate (measure actual vs. spec, adjust VFD)",
                    "Adjust guide rails for current container diameter — should be container width + 1/4\" max",
                    "Reduce accumulation table back-pressure by adjusting sweep arm timing or conveyor speed",
                ],
                "pm_additions": [
                    "Changeover: always verify guide rail width for new container size before running",
                    "Weekly: inspect guide rail UHMW wear strips for grooves or flat spots",
                    "Monthly: calibrate infeed conveyor speed sensor",
                ],
            },
            {
                "mode": "Low Air Pressure",
                "likely_cause": "Pneumatic system pressure drop below operating threshold, causing actuators to move slowly or incompletely. Often intermittent, correlating with high demand from multiple pneumatic devices.",
                "root_causes": [
                    "Air leaks in flex hoses or quick-connect fittings — pressure drops under load when multiple cylinders fire simultaneously",
                    "Air compressor capacity insufficient for peak demand — common after adding pneumatic equipment without upgrading supply",
                    "FRL (Filter-Regulator-Lubricator) unit clogged or regulator failing — pressure drops downstream of the FRL while header pressure is normal",
                ],
                "fixes": [
                    "Ultrasonic leak test on all pneumatic connections — fix leaks starting from highest flow rate",
                    "Install a pressure gauge downstream of FRL and compare to header — if >5 PSI drop, service FRL",
                    "Map pneumatic demand vs. supply capacity — if peak demand exceeds 80% of compressor output, add receiver tank or upgrade",
                ],
                "pm_additions": [
                    "Weekly: check FRL drain bowl and filter element",
                    "Monthly: ultrasonic leak survey on all pneumatic connections",
                    "Quarterly: verify compressor output pressure and cycle time",
                ],
            },
            {
                "mode": "Safety Interlock",
                "likely_cause": "Safety interlock tripped, requiring manual reset. Usually a guard door opened during operation or an E-stop activated. Frequent trips indicate either a maintenance access issue or a sensor fault.",
                "root_causes": [
                    "Guard door interlock switch misaligned — vibration causes intermittent trips during normal operation",
                    "Operators opening guards to clear jams without proper lockout — interlock working as designed but indicating a jam problem upstream",
                    "Light curtain dirty or misaligned — false trips from dust, moisture, or vibration",
                ],
                "fixes": [
                    "Re-align interlock switches with 2-3mm engagement margin and tighten mounting hardware with thread-lock",
                    "If trips correlate with jams: fix the root jam cause rather than treating the interlock as the problem",
                    "Clean light curtain lenses and check alignment — realign per manufacturer spec if dirty environment",
                ],
                "pm_additions": [
                    "Weekly: visual check of all guard door interlock switches for looseness",
                    "Monthly: function-test each safety interlock (verify it actually stops the machine)",
                    "Daily: wipe light curtain lenses if in dusty/humid environment",
                ],
            },
        ],
    },
    "labeler": {
        "name": "Labeler",
        "failure_modes": [
            {
                "mode": "Label Misalignment / Skew",
                "likely_cause": "Labels applying off-center or at an angle, typically due to web tension issues or worn applicator components.",
                "root_causes": [
                    "Web tension inconsistent — label stock stretching or slack causing lateral drift",
                    "Applicator roller or pad worn unevenly — one side applying more pressure than the other",
                    "Product orientation inconsistent at label station — containers rotating between detection and application",
                ],
                "fixes": [
                    "Calibrate web tension to label stock spec (typically 2-4 lbs for standard paper labels)",
                    "Inspect and replace applicator pad/roller if wear exceeds 0.5mm unevenness",
                    "Add or adjust product orientation guides upstream of label station",
                ],
                "pm_additions": [
                    "Daily: check web tension reading at startup",
                    "Weekly: inspect applicator pad for uneven wear",
                    "Monthly: verify label sensor calibration",
                ],
            },
            {
                "mode": "Label Stock Out / Splice Fault",
                "likely_cause": "Label roll depleted or splice between rolls not feeding through smoothly, causing a line stop while operator loads new roll.",
                "root_causes": [
                    "No low-label warning sensor — operator doesn't know roll is running out until it stops",
                    "Splice tape or splice angle incompatible with feed mechanism — new roll catches and jams",
                    "Roll core diameter varies between suppliers — tension arm range doesn't accommodate the difference",
                ],
                "fixes": [
                    "Install or recalibrate low-label sensor to trigger warning at 10-15% remaining",
                    "Standardize splice procedure: 45-degree angle cut, specific splice tape, butt splice (not overlap)",
                    "Measure core ID from each supplier and adjust tension arm limits accordingly",
                ],
                "pm_additions": [
                    "Changeover: verify new label roll specs match previous",
                    "Weekly: clean label feed path and sensors",
                    "Monthly: inspect tension arm springs and bearings",
                ],
            },
        ],
    },
    "depalletizer": {
        "name": "Depalletizer",
        "failure_modes": [
            {
                "mode": "Can/Container Jam at Sweep",
                "likely_cause": "Containers jamming during sweep arm transfer from pallet layer to conveyor. Often caused by layer pad issues or sweep speed mismatch.",
                "root_causes": [
                    "Layer pad not fully removed before sweep — containers catch on pad edge",
                    "Sweep arm speed too fast for container type — tall/light containers tip during sweep",
                    "Container pattern on pallet doesn't match depal recipe — containers at edges not aligned for sweep",
                ],
                "fixes": [
                    "Verify pad picker vacuum cups and timing — pad must be fully clear before sweep begins",
                    "Reduce sweep speed for tall/light containers and increase guide rail height at sweep zone",
                    "Confirm pallet pattern matches depal recipe — update recipe if supplier changed pack pattern",
                ],
                "pm_additions": [
                    "Daily: inspect vacuum cups on pad picker for wear/cracking",
                    "Weekly: verify sweep arm timing and speed settings",
                    "Monthly: calibrate layer height sensor",
                ],
            },
            {
                "mode": "Pallet Jam / Pallet Not Detected",
                "likely_cause": "Pallet not feeding into depalletizer correctly or not being detected by sensor, causing the machine to fault.",
                "root_causes": [
                    "Pallet infeed conveyor rollers worn or seized — pallet doesn't advance to correct position",
                    "Pallet detection sensor dirty or misaligned — doesn't see pallet even when present",
                    "Non-standard pallet dimensions (especially height) — triggers fault due to unexpected geometry",
                ],
                "fixes": [
                    "Replace worn conveyor rollers at pallet infeed — check for seized bearings",
                    "Clean and realign pallet detection sensors (photo-eye or proximity)",
                    "Add pallet inspection step at receiving — reject out-of-spec pallets before they reach depal",
                ],
                "pm_additions": [
                    "Weekly: clean all photo-eyes and proximity sensors at depal infeed",
                    "Monthly: inspect infeed conveyor rollers and chains for wear",
                    "Quarterly: verify pallet centering guides are within spec",
                ],
            },
        ],
    },
    "filler": {
        "name": "Filler",
        "failure_modes": [
            {
                "mode": "Fill Level Variance / Overfill / Underfill",
                "likely_cause": "Product fill level outside specification, typically caused by pump inconsistency, temperature-related viscosity changes, or worn fill nozzle components.",
                "root_causes": [
                    "Fill pump diaphragm or piston seal worn — delivering inconsistent volume per stroke",
                    "Product temperature changing fill viscosity — cold product fills differently than warm",
                    "Fill nozzle orifice partially clogged with product buildup — some nozzles filling less than others",
                ],
                "fixes": [
                    "Replace pump seals and diaphragms if fill variance exceeds ±2% of target across nozzles",
                    "Verify product temperature at filler bowl is within spec (±3°F) — adjust heating/cooling if drifting",
                    "CIP and inspect all fill nozzles — compare individual nozzle fill weights to identify partial blockages",
                ],
                "pm_additions": [
                    "Every changeover: check fill weights from each nozzle individually",
                    "Weekly: inspect pump seals for wear",
                    "Monthly: full fill nozzle disassembly and cleaning",
                ],
            },
        ],
    },
    "seamer": {
        "name": "Seamer / Closer",
        "failure_modes": [
            {
                "mode": "Seam Defect / Loose Seam",
                "likely_cause": "Can seam not meeting double-seam specifications, risking product safety. Critical food safety issue.",
                "root_causes": [
                    "First or second operation roll worn — not applying correct seam profile",
                    "Seamer chuck worn or damaged — not holding can body securely during seaming",
                    "Can flange damaged upstream (dented at conveyor transition) — seam cannot form correctly on damaged flange",
                ],
                "fixes": [
                    "Measure seam parameters (overlap, tightness, countersink) and compare to spec — replace rolls if out of tolerance",
                    "Inspect and replace chucks if runout exceeds 0.002\"",
                    "Trace flange damage to upstream cause — usually a conveyor transition or timing screw issue",
                ],
                "pm_additions": [
                    "Every 4 hours: destructive seam teardown and measurement (per plant SOP)",
                    "Weekly: visual seam inspection across all heads",
                    "Monthly: measure chuck runout and roll clearances",
                ],
            },
        ],
    },
    "wrapper": {
        "name": "Shrink Wrapper",
        "failure_modes": [
            {
                "mode": "Film Out / Film Break",
                "likely_cause": "Shrink film depleted or broke during operation, requiring rethreading.",
                "root_causes": [
                    "Film tension set too high for current film gauge — thin film breaks under tension",
                    "Film splicing done improperly — splice doesn't hold through wrapper feed mechanism",
                    "Hot wire seal bar temperature too high — melting through film instead of sealing",
                ],
                "fixes": [
                    "Verify film tension for current film spec — reduce tension 10-15% if breaks are frequent",
                    "Retrain operators on proper film splicing technique for this specific wrapper model",
                    "Check seal bar temperature with contact thermometer — should be within 5°F of spec for film type",
                ],
                "pm_additions": [
                    "Daily: verify seal bar temperature at startup",
                    "Weekly: inspect film feed rollers for wear/contamination",
                    "Monthly: calibrate tension control system",
                ],
            },
            {
                "mode": "Hot Wire Fault / Seal Failure",
                "likely_cause": "Hot wire or seal bar not cutting/sealing properly, producing open or weak seals.",
                "root_causes": [
                    "Hot wire element worn or degraded — uneven heating across wire length",
                    "PTFE tape on seal bar worn through — film sticking to bar instead of sealing cleanly",
                    "Seal time/temperature mismatch for current film type — parameters not updated after film supplier change",
                ],
                "fixes": [
                    "Replace hot wire element — keep spares on hand (consumable, 2-4 week life depending on usage)",
                    "Replace PTFE tape on seal bars — inspect daily for wear-through",
                    "Document seal parameters per film type/gauge — post chart at machine for operators",
                ],
                "pm_additions": [
                    "Daily: visual check of PTFE tape condition",
                    "Weekly: measure seal bar temperature uniformity across length",
                    "Bi-weekly: replace hot wire element (preventive, don't wait for failure)",
                ],
            },
            {
                "mode": "Exit Conveyor Busy",
                "likely_cause": "Downstream conveyor backed up, causing wrapper to fault on exit conveyor full condition.",
                "root_causes": [
                    "Downstream equipment (palletizer, accumulation table) running slower than wrapper — backs up to wrapper exit",
                    "Conveyor photoeye blocked by product debris or misaligned — false 'full' signal",
                    "Case or tray ejected at bad angle — stuck on exit conveyor transition point",
                ],
                "fixes": [
                    "Balance line speeds: wrapper output must not exceed downstream capacity by more than 5%",
                    "Clean and verify exit conveyor photoeyes — check alignment with reflectors",
                    "Inspect exit conveyor transition plates and guide rails for snag points",
                ],
                "pm_additions": [
                    "Daily: clean exit conveyor photoeyes",
                    "Weekly: verify downstream equipment speeds match wrapper output",
                    "Monthly: inspect transition plates for wear or misalignment",
                ],
            },
        ],
    },
    "palletizer": {
        "name": "Palletizer",
        "failure_modes": [
            {
                "mode": "Layer Pattern Error / Misstack",
                "likely_cause": "Cases not forming correct layer pattern, resulting in unstable pallets or machine fault.",
                "root_causes": [
                    "Pattern recipe incorrect or corrupted — case count or orientation doesn't match physical product",
                    "Case squareness issue from upstream caser — slightly rhomboid cases don't align in pattern",
                    "Pusher/sweep timing off — cases not in position when layer transfer occurs",
                ],
                "fixes": [
                    "Verify pattern recipe against actual case dimensions — rebuild pattern if case size changed",
                    "Check upstream caser case squareness with a machinist square — adjust if diagonal difference > 1/4\"",
                    "Re-time pusher/sweep sequence — verify with slow-speed test before production speed",
                ],
                "pm_additions": [
                    "Changeover: verify pattern recipe matches product being run",
                    "Weekly: check pusher/sweep timing against baseline",
                    "Monthly: inspect layer forming guides and stops for wear",
                ],
            },
        ],
    },
    "conveyor": {
        "name": "Conveyor System",
        "failure_modes": [
            {
                "mode": "Jam / Blockage",
                "likely_cause": "Product jamming at conveyor transitions, dead plates, or merge points. Most common single cause of micro-stops.",
                "root_causes": [
                    "Dead plate gap between conveyor sections too wide — product catches and tips",
                    "Guide rail width incorrect for product size — too tight causes binding, too loose allows rotation",
                    "Conveyor speed differential at merge/divert points — product colliding instead of flowing",
                ],
                "fixes": [
                    "Measure and adjust dead plate gaps to < 1/4\" (for cans) or < 1/2\" (for cases)",
                    "Set guide rails to product width + 1/4\" for cans, + 1/2\" for cases",
                    "Map conveyor speeds at all transitions — downstream must be 5-10% faster than upstream",
                ],
                "pm_additions": [
                    "Daily: visual walk of all conveyor transitions during startup",
                    "Weekly: measure and log dead plate gaps at top 5 jam points",
                    "Monthly: verify all conveyor VFD speed settings against baseline",
                ],
            },
        ],
    },
    "shrink_tunnel": {
        "name": "Shrink Tunnel",
        "failure_modes": [
            {
                "mode": "Insufficient Shrink / Dog Ears",
                "likely_cause": "Shrink film not fully shrinking around product, leaving loose corners ('dog ears') or unshrunk areas.",
                "root_causes": [
                    "Tunnel temperature too low for film type — film isn't reaching shrink activation temperature",
                    "Conveyor speed through tunnel too fast — insufficient dwell time at temperature",
                    "Air circulation uneven — dead spots in tunnel where film doesn't shrink uniformly",
                ],
                "fixes": [
                    "Verify tunnel temperature matches film manufacturer spec (typically 300-375°F for PE, 250-325°F for PVC)",
                    "Reduce tunnel conveyor speed until shrink is complete — balance against line throughput",
                    "Check air circulation fans and baffles — clean or replace if airflow is uneven",
                ],
                "pm_additions": [
                    "Daily: verify tunnel temperature at startup (check both zones if dual-zone)",
                    "Weekly: clean air circulation fans and inspect baffles",
                    "Monthly: calibrate temperature controllers with external thermocouple",
                ],
            },
        ],
    },
    "x-ray": {
        "name": "X-Ray Inspection System",
        "failure_modes": [
            {
                "mode": "False Rejects / High Reject Rate",
                "likely_cause": "X-ray system rejecting good product, reducing throughput and creating waste.",
                "root_causes": [
                    "Detection sensitivity set too high for current product density — normal product variation triggers rejects",
                    "Product positioning inconsistent — containers entering X-ray at different orientations give different density profiles",
                    "X-ray source degrading — lower output produces noisier images, increasing false positives",
                ],
                "fixes": [
                    "Run sensitivity optimization: test with known-good product to find lowest sensitivity that still catches test pieces",
                    "Add product orientation guides upstream of X-ray to ensure consistent positioning",
                    "Check X-ray source output (kV and mA) against installation baseline — schedule tube replacement if degraded >10%",
                ],
                "pm_additions": [
                    "Every shift: run test piece verification (per HACCP plan)",
                    "Weekly: clean detector array and inspect conveyor belt",
                    "Monthly: log X-ray source output and trend against baseline",
                ],
            },
        ],
    },
    "print_apply": {
        "name": "Print & Apply / Date Coder",
        "failure_modes": [
            {
                "mode": "Print Quality Failure / Misprint",
                "likely_cause": "Date codes or labels printing illegibly or in wrong position, causing quality holds.",
                "root_causes": [
                    "Printhead clogged (inkjet) or ribbon wrinkled (thermal transfer) — print quality degrades over time",
                    "Product detection sensor timing off — printing at wrong position on container",
                    "Ink/ribbon stock incompatible with substrate — code doesn't adhere or smears",
                ],
                "fixes": [
                    "Clean printhead per manufacturer schedule — auto-purge is often insufficient, manual cleaning needed",
                    "Recalibrate detection sensor delay vs. conveyor speed — verify with slow and fast speed",
                    "Verify ink/ribbon compatibility with current packaging material — get sample tested if substrate changed",
                ],
                "pm_additions": [
                    "Daily: check print quality sample at startup and after each changeover",
                    "Weekly: manual printhead cleaning (beyond auto-purge)",
                    "Monthly: verify detection sensor alignment and timing",
                ],
            },
        ],
    },
    "accumulation_table": {
        "name": "Accumulation Table",
        "failure_modes": [
            {
                "mode": "Product Tipping / Jam at Discharge",
                "likely_cause": "Containers tipping on the accumulation table, especially at discharge where they transition back to single-file conveyor.",
                "root_causes": [
                    "Table surface speed too fast relative to conveyor takeaway — pressure buildup at discharge",
                    "Discharge funnel geometry not matched to container type — tall/narrow containers tip at the transition",
                    "Table not level — product drifts to one side creating uneven pressure at discharge",
                ],
                "fixes": [
                    "Reduce table speed to match downstream conveyor demand — table should empty smoothly, not pressure-feed",
                    "Adjust discharge funnel guides for current container — narrower funnel for smaller containers",
                    "Level the table with precision level — should be flat to within 1/8\" across full surface",
                ],
                "pm_additions": [
                    "Changeover: adjust discharge funnel for new container size",
                    "Weekly: check table surface for wear, sticky spots, or debris",
                    "Monthly: verify table is level",
                ],
            },
        ],
    },
}


def get_static_fixes(equipment_name: str) -> dict | None:
    """Look up static KB entry by equipment name (fuzzy match)."""
    name_lower = equipment_name.lower().strip()

    # Score each entry — highest specificity wins
    best_score = 0
    best_entry = None

    for key, entry in EQUIPMENT_KB.items():
        score = 0
        entry_name_lower = entry["name"].lower()

        # Exact key match
        if key == name_lower:
            score = 100
        # Key in name or name in key
        elif key in name_lower:
            score = 50 + len(key)  # longer key match = more specific
        elif name_lower in key:
            score = 40

        # Word overlap with entry name
        if score == 0:
            entry_words = set(entry_name_lower.replace("/", " ").split())
            name_words = set(name_lower.replace("-", " ").replace("_", " ").split())
            # Remove short/common words
            entry_words = {w for w in entry_words if len(w) > 2}
            name_words = {w for w in name_words if len(w) > 2}
            overlap = entry_words & name_words
            if overlap:
                score = 10 + len(overlap) * 5

        if score > best_score:
            best_score = score
            best_entry = entry

    return best_entry if best_score > 0 else None


def format_kb_for_prompt(equipment_names: list[str]) -> str:
    """Format static KB entries as context for the LLM fix researcher."""
    sections: list[str] = []

    for name in equipment_names:
        entry = get_static_fixes(name)
        if entry is None:
            continue

        lines = [f"\n=== {entry['name']} — Known Failure Modes ==="]
        for fm in entry["failure_modes"]:
            lines.append(f"\nMode: {fm['mode']}")
            lines.append(f"Likely cause: {fm['likely_cause']}")
            lines.append("Root causes:")
            for i, rc in enumerate(fm["root_causes"], 1):
                lines.append(f"  {i}. {rc}")
            lines.append("Standard fixes:")
            for i, fix in enumerate(fm["fixes"], 1):
                lines.append(f"  {i}. {fix}")
            lines.append("PM additions:")
            for pm in fm["pm_additions"]:
                lines.append(f"  - {pm}")

        sections.append("\n".join(lines))

    return "\n".join(sections)
