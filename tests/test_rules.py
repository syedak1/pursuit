"""Rules are the part of the pipeline most likely to regress silently, so they get tests.
Every case below is a real Ann Arbor title or memo sentence (lightly trimmed)."""

from clock.rules import categorize, is_funding, is_purchase, parse_text, parse_title, vendor_key
from clock.text import normalize, sentence_around, verify


def fields(hits):
    return {h.field: h.value for h in hits}


def test_title_sole_source_professional_services():
    t = ("Resolution to Approve a Sole Source Professional Services Agreement with Covalence Consulting Inc., for UKG Pro "
         "Support of the Transition of the City from Ultimate Time and Attendance (UTA) to UKG Pro Workforce Management "
         "(WFM) Platform and Appropriate Funds ($279,400.00) (8 Votes Required)")
    f = fields(parse_title(t))
    assert {k: f[k] for k in ("kind", "route", "vendor", "amount")} == {
        "kind": "professional_services", "route": "sole_source", "vendor": "Covalence Consulting Inc.", "amount": 279400.0}
    assert f["amount_basis"] == "stated"
    assert is_purchase(t, parse_title(t))
    assert "it_software" in categorize(t, "Information Technology Services")


def test_title_dba_vendor_and_itb():
    t = ("Resolution to approve a General Services Agreement with RACM, L.L.C., D/B/A Servpro Team Miller, for Water Damage "
         "Remediation Services ($170,000.00, ITB No. 4790)")
    f = fields(parse_title(t))
    assert f["vendor"] == "RACM, L.L.C., D/B/A Servpro Team Miller"
    assert f["route"] == "competitive"
    assert vendor_key(f["vendor"]) == "servpro team miller"
    assert "water_utilities" not in categorize(t, "Public Works")  # water *damage* is not water infrastructure


def test_title_increase_takes_new_ceiling():
    t = "Resolution to Approve an Increase to the FY27 Sole Source Purchase Order with Brown Equipment Company from $25,000.00 to $70,000.00"
    f = fields(parse_title(t))
    assert f["vendor"] == "Brown Equipment Company"
    assert f["amount"] == 70000.0


def test_title_first_amount_not_project_budget():
    t = ("Resolution to Approve a Professional Services Agreement with Baker and Associates for Inspection Services "
         "($124,178.47) (RFP No. 24-35) and Establish a Project Budget for $175,000.00")
    assert fields(parse_title(t))["amount"] == 124178.47


def test_title_cooperative():
    t = "Resolution to Approve the Purchase of Vehicles from National Auto Fleet Group (Sourcewell Bid - $111,308.00)"
    f = fields(parse_title(t))
    assert f["route"] == "cooperative" and f["vendor"] == "National Auto Fleet Group"


def test_not_purchases():
    for t in ["Resolution to Approve a Payment in Lieu of Taxes (PILOT) for the Affordable Housing Project at 2810 Boardwalk",
              "Resolution Authorizing the City Attorney to Take Legal Action to Enforce the City's 2006 Settlement Agreement with Gelman Sciences, Inc.",
              "Resolution to Approve a Renewal of the Uniform Video Service Local Franchise Agreement with DIRECTV, LLC"]:
        assert not is_purchase(t, parse_title(t)), t


def test_funding():
    assert is_funding("Resolution to Appropriate and Increase the FY 2027 Office of Sustainability and Innovations Climate Action Millage Expenditure Budget by $874,467.00 (8 Votes Required)")
    assert is_funding("Resolution to Accept and Appropriate a $500,000.00 Grant from the Community Foundation for Southeast Michigan for the South Barton Pedestrian Bridge Replacement Project")


def test_memo_terms_dates_renewals():
    m = ("recommends that Du-All be approved as the lowest responsible bidder to provide janitorial services at the WWTP "
         "starting on September 1, 2022 through August 31, 2025. Additionally, approval is recommended to allow the City "
         "Administrator to approve extensions of the contract for up to two additional one-year terms at no increase in cost.")
    f = fields(parse_text(m))
    assert f["start_date"] == "2022-09-01" and f["end_date"] == "2025-08-31"
    assert f["renewals"] == {"count": 2, "months_each": 12}
    assert f["route"] == "competitive"


def test_memo_ignores_pricing_deadline_and_history():
    m = "Whereas, The bid prices are firm through May 10, 2023 unless manufacturers declare a force majeure;"
    assert "end_date" not in fields(parse_text(m))
    m = ("As background, for over three (3) years, City staff have been working with the residents of the Bryant "
         "neighborhood to determine what it would look like.")
    assert "term_months" not in fields(parse_text(m))


def test_memo_ignores_cip_horizon():
    m = "Budget/Fiscal Impact: This project is included in the FY23-28 Capital Improvements Plan (UT SN 19-01)."
    assert "fy_range" not in fields(parse_text(m))


def test_verify_is_exact_after_normalization():
    src = "The contract would run\nthrough June 30, 2027."
    assert verify("The contract would run through June 30, 2027.", src)[0]
    assert not verify("The contract runs through June 30, 2027.", src)[0]  # paraphrase fails


def test_sentence_does_not_split_on_inc():
    t = normalize("A PSA with Acme Inc. for design. The term is three years.")
    i = t.index("Acme")
    lo, hi = sentence_around(t, i, i + 4)
    assert t[lo:hi] == "A PSA with Acme Inc. for design."


def test_agreement_to_purchase_names_the_right_vendor():
    t = "Resolution to Approve the Agreement to Purchase Parking Technology and Related Services with IPS Group, Inc. ($1,209,442.28)"
    assert fields(parse_title(t))["vendor"] == "IPS Group, Inc."
    t = "Resolution to Approve a Purchase Order to AmeriNet of Michigan, Inc. for a Three-Year Network Equipment Agreement ($327,950.64)"
    assert fields(parse_title(t))["vendor"] == "AmeriNet of Michigan, Inc."


def test_staff_header():
    from clock.rules import parse_staff
    m = ("..Staff Prepared by: Missy Stults, Sustainability and Innovations Director Reviewed by: Marti Praschan, "
         "Chief Financial Officer Approved by: Milton Dohoney Jr., City Administrator ..Body Whereas, In 2022")
    f = fields(parse_staff(m))
    assert f["prepared_by"] == {"name": "Missy Stults", "title": "Sustainability and Innovations Director"}
    assert f["reviewed_by"] == {"name": "Marti Praschan", "title": "Chief Financial Officer"}
    m = "Prepared by: Brian Steglitz, PE, Interim Public Services Area Administrator Reviewed by: X"
    assert fields(parse_staff(m))["prepared_by"]["name"] == "Brian Steglitz, PE"


def test_vendor_shapes_from_real_titles():
    cases = {
        "Resolution to Approve Change Order No. 1 with Z Contractors, Inc. for the Huron Parkway Bridge Capital Preventative Maintenance Project ($86,059.75 Increase, Total Contract $1,000,000.00)": "Z Contractors, Inc.",
        "Resolution to Approve Amendment No. 1 to the Professional Services Agreement with NTH Consultants, Ltd. for Barton Dam Right Embankment Remediation ($214,102.47)": "NTH Consultants, Ltd.",
        "Resolution to Approve a Professional Services Agreement with 5 Lakes Energy, LLC to Complete a Feasibility Study ($75,000.00)": "5 Lakes Energy, LLC",
        "Resolution to Approve the Purchasing Agreement for Utility Infrastructure Materials from Core and Main LP, ITB-4715 ($923,083.71)": "Core and Main LP",
        "Resolution to Authorize a Best Source Purchase Order for Removal of Residuals to Prolime Corporation (Not to Exceed $270,000.00)": "Prolime Corporation",
        "Resolution to Approve Renewal 3 to the Professional Services Agreement between Carlisle/Wortman Associates, Inc. and the City of Ann Arbor for On-Call Planning ($50,000.00)": "Carlisle/Wortman Associates, Inc.",
        "Resolution to Approve a Sole Source Purchase Order to Service Electric Supply, Inc. for Large Electric Motor Soft Starters ($60,000.00)": "Service Electric Supply, Inc.",
        "Resolution to Amend Purchasing Authorization for FY24 and FY25 with MacQueen Equipment, LLC of Lake Orion, Michigan, for Repair Parts ($150,000.00)": "MacQueen Equipment, LLC",
        "Resolution to Approve a Legal Services Agreement with Rosati, Schultz, Joppich & Amtsbeuchler, PC Relative to City Projects ($60,000.00)": "Rosati, Schultz, Joppich & Amtsbeuchler, PC",
    }
    for title, vendor in cases.items():
        assert fields(parse_title(title)).get("vendor") == vendor, title


def test_public_bodies_are_not_vendors():
    from clock.rules import is_intergovernmental
    t = "Resolution to Approve a Cost Sharing Agreement with the Downtown Development Authority for the Downtown Area Circulation Study ($250,000.00)"
    assert "vendor" not in fields(parse_title(t)) and is_intergovernmental(t)
    t = "Resolution Approving a Contract with the Shelter Association of Washtenaw County for the 2024-2025 Winter Emergency Shelter ($100,000.00)"
    assert fields(parse_title(t))["vendor"] == "Shelter Association of Washtenaw County"  # a nonprofit, not the county


def test_amount_basis():
    assert fields(parse_title("Resolution to Approve a Purchase Order with D3W Industries, Inc. for Odor Control Chemicals ($308,026.00 Annually)"))["amount_basis"] == "annual"
    assert fields(parse_title("Resolution to Approve a Purchase Order with Acme Inc. for Salt (Not to Exceed $242,825.00)"))["amount_basis"] == "ceiling"
    assert fields(parse_title("Resolution to Approve Change Order No. 1 with Doan Construction Co. for Sidewalks ($200,678.81, Total Contract Amount $772,641.94)"))["amount_basis"] == "total"


def test_approval_state():
    from clock.build import approval_state
    assert approval_state("Passed", "2026-09-22") == "approved"
    assert approval_state("Consent Agenda", None) == "pending"
    assert approval_state("Defeated", None) == "not_approved"


def test_more_term_shapes():
    f = fields(parse_text("Whereas, The term of the proposed contract with RACM, L.L.C., D/B/A Servpro Team Miller is for two-years and up to $170,000.00;"))
    assert f["term_months"] == 24
    f = fields(parse_text("Memorandum: a resolution to award a two-year general services contract with Acme, Inc. for repairs."))
    assert f["term_months"] == 24
    f = fields(parse_text("RESOLVED, That the City Administrator be authorized to renew the purchase order for up to three one-year periods provided both parties agree;"))
    assert f["renewals"] == {"count": 3, "months_each": 12}
    f = fields(parse_text("The agreement includes the option of one two (2)-year extension upon mutual agreement."))
    assert f["renewals"] == {"count": 1, "months_each": 24}
    f = fields(parse_text("The Office built funds into its FY26 and FY27 budgets for work under this contract."))
    assert f["fy_range"] == {"from": 2026, "to": 2027}
    f = fields(parse_text("Issuance of the FY27 purchase order and any approved extension for FY28 and FY29 would be subject to funds."))
    assert "fy_range" not in f


def test_prices_are_not_contract_ends():
    m = "The change order updates the locations and extends contract prices through October 1, 2026."
    assert "end_date" not in fields(parse_text(m))
    f = fields(parse_text("Whereas, The bid prices are firm through August 31, 2027;"))
    assert f["prices_until"] == "2027-08-31" and "end_date" not in f


def test_staff_header_with_several_reviewers():
    from clock.rules import parse_staff
    t = ("Memorandum Prepared by: Jake Chase, IT Manager Reviewed by: Tom Shewchuk, Director, Information "
         "Technology Services Unit Kim Hoenerhoff, Financial Analyst .. Summary: ...")
    hits = {h.field: h.value for h in parse_staff(t)}
    assert hits["prepared_by"] == {"name": "Jake Chase", "title": "IT Manager"}
    assert hits["reviewed_by"] == {"name": "Tom Shewchuk", "title": "Director, Information Technology Services Unit"}
    t2 = "Prepared By: Ana Ruiz, Manager, Systems Planning, Public Services Reviewed By: Derek Delacourt, Community Services Area Administrator"
    hits = {h.field: h.value for h in parse_staff(t2)}
    assert hits["prepared_by"]["title"] == "Manager, Systems Planning, Public Services"
    assert hits["reviewed_by"]["name"] == "Derek Delacourt"


def test_incumbent_since_from_memo():
    from clock.rules import parse_incumbent_since
    t = ("The City has a perpetual license. The current maintenance agreement with Cogsdale Corporation has been in "
         "place since 2018 and automatically renews annually subject to appropriation.")
    h = parse_incumbent_since(t, "Cogsdale Corporation")
    assert h and h.value == 2018
    # A "since" about something else, or without the vendor nearby, is not incumbency.
    assert parse_incumbent_since("Prices have been in place since 2019 for all vendors.", "Cogsdale Corporation") is None


def test_auto_renewal():
    from clock.rules import parse_auto_renew
    assert parse_auto_renew("The agreement automatically renews annually subject to appropriation.").value is True
    assert parse_auto_renew("A one-year lease with up to 5 automatic renewals.").value is True
    assert parse_auto_renew("Drainage improvements near the Evergreen Subdivision.") is None


def test_competitive_phrasings_seen_in_memos():
    # Each of these was "method not stated" until the rule learned the phrasing.
    for m in [
        "The City issued Request for Proposal (RFP) No. 22-05 for professional engineering services.",
        "a resolution to approve Extension No. 1 to the Contract with P.K. Contracting, LLC for pavement marking maintenance (RFP: 22-38)",
        "Of the six proposals received, WRRF staff selected Fishbeck, HRC, and OHM based on their professional qualifications.",
        "In 2022, the City Safety Unit issued a request for proposal for qualified vendors and provided intent to award to Henry Ford Health.",
    ]:
        assert fields(parse_text(m)).get("route") == "competitive", m
    t = "Resolution to Approve a Two (2) Year Purchasing Agreement with Cadillac Asphalt, LLC for Bituminous Patching Materials, ITB-4724 ($136,500.00 Annually)"
    assert fields(parse_title(t))["route"] == "competitive"


def test_future_rfp_is_not_the_award_method():
    for m in [
        "This purchase order will enable us to continue current services until a new RFP can be advertised and a new contract executed.",
        "we will evaluate the feasibility of a new professional services agreement with extended timing, or we will explore completing an updated RFP.",
    ]:
        assert "route" not in fields(parse_text(m)), m
