"""
India AI-Infrastructure Universe — wide-net basket.

Themes covered: data center landlords/EPC, cables (power+fiber), optics & networks,
semis/OSAT, power equipment (switchgear, transformers, gensets, gas turbines, fuel
cells), cooling, oil/gas/hydrogen, construction, and adjacencies.

Schema mirrors INDIA_UNIVERSE in fetch_etf_data.py:
  key → (display_name, yf_ticker, mfapi_codes_unused, theme_tag)

Use with: from ai_infra_universe import AI_INFRA_UNIVERSE
"""

# (display_name, yfinance_ticker, mfapi_codes (unused for stocks), theme)
AI_INFRA_UNIVERSE: dict[str, tuple[str, str, list[int], str]] = {
    # === DC Landlords + Builders + Hyperscaler-named ===
    "ADANIENT":     ("Adani Enterprises",          "ADANIENT.NS",   [], "DC:Landlord"),
    "ADANIPOWER":   ("Adani Power",                "ADANIPOWER.NS", [], "DC:Landlord"),
    "ADANIGREEN":   ("Adani Green Energy",         "ADANIGREEN.NS", [], "DC:Landlord"),
    "BHARTIARTL":   ("Bharti Airtel (Nxtra)",      "BHARTIARTL.NS", [], "DC:Landlord"),
    "RELIANCE":     ("Reliance Industries",        "RELIANCE.NS",   [], "DC:Landlord"),
    "TATACOMM":     ("Tata Communications",        "TATACOMM.NS",   [], "DC:Landlord"),
    "TATAPOWER":    ("Tata Power",                 "TATAPOWER.NS",  [], "DC:Landlord"),
    "LT":           ("Larsen & Toubro",            "LT.NS",         [], "DC:Landlord"),
    "ANANTRAJ":     ("Anant Raj",                  "ANANTRAJ.NS",   [], "DC:Landlord"),

    # === Tata adjacencies ===
    "TATAELXSI":    ("Tata Elxsi",                 "TATAELXSI.NS",  [], "Semi:ER&D"),
    "TCS":          ("Tata Consultancy Services",  "TCS.NS",        [], "DC:IT-Svcs"),

    # === Power Cables ===
    "POLYCAB":      ("Polycab India",              "POLYCAB.NS",    [], "Cable:Power"),
    "KEI":          ("KEI Industries",             "KEI.NS",        [], "Cable:Power"),
    "APARINDS":     ("Apar Industries",            "APARINDS.NS",   [], "Cable:Power"),
    "RRKABEL":      ("RR Kabel",                   "RRKABEL.NS",    [], "Cable:Power"),
    "FINCABLES":    ("Finolex Cables",             "FINCABLES.NS",  [], "Cable:Power"),
    "HAVELLS":      ("Havells India",              "HAVELLS.NS",    [], "Cable:Power"),

    # === Optics + Fiber + Network ===
    "STLTECH":      ("Sterlite Technologies",      "STLTECH.NS",    [], "Optic:Fiber"),
    "HFCL":         ("HFCL",                       "HFCL.NS",       [], "Optic:Fiber"),
    "TEJASNET":     ("Tejas Networks",             "TEJASNET.NS",   [], "Net:Gear"),
    "ITI":          ("ITI Limited",                "ITI.NS",        [], "Net:Gear"),
    "AKSHOPTFBR":   ("Aksh Optifibre",             "AKSHOPTFBR.NS", [], "Optic:Fiber"),

    # === Semis / OSAT / Substrates ===
    "CGPOWER":      ("CG Power & Industrial",      "CGPOWER.NS",    [], "Semi:OSAT+Power"),
    "KAYNES":       ("Kaynes Technology",          "KAYNES.NS",     [], "Semi:OSAT"),
    "SYRMA":        ("Syrma SGS",                  "SYRMA.NS",      [], "Semi:EMS"),
    "DIXON":        ("Dixon Technologies",         "DIXON.NS",      [], "Semi:EMS"),

    # === Power: Switchgear + Transformers ===
    "POWERINDIA":   ("Hitachi Energy India",       "POWERINDIA.NS", [], "Power:Switchgear"),
    "ABB":          ("ABB India",                  "ABB.NS",        [], "Power:Switchgear"),
    "SIEMENS":      ("Siemens India",              "SIEMENS.NS",    [], "Power:Switchgear"),
    "VOLTAMP":      ("Voltamp Transformers",       "VOLTAMP.NS",    [], "Power:Transformer"),
    "TARIL":        ("Transformers & Rectifiers",  "TARIL.NS",      [], "Power:Transformer"),

    # === Power: Gensets + Turbines + Fuel Cells ===
    "CUMMINSIND":   ("Cummins India",              "CUMMINSIND.NS", [], "Power:Genset"),
    "KIRLOSENG":    ("Kirloskar Oil Engines",      "KIRLOSENG.NS",  [], "Power:Genset"),
    "TRITURBINE":   ("Triveni Turbine",            "TRITURBINE.NS", [], "Power:Turbine"),
    "MTARTECH":     ("MTAR Technologies",          "MTARTECH.NS",   [], "Power:FuelCell"),
    "THERMAX":      ("Thermax",                    "THERMAX.NS",    [], "Power:EPC"),
    "BHEL":         ("BHEL",                       "BHEL.NS",       [], "Power:EPC"),
    "BHARATFORG":   ("Bharat Forge",               "BHARATFORG.NS", [], "Power:Forging"),

    # === Cooling ===
    "BLUESTARCO":   ("Blue Star",                  "BLUESTARCO.NS", [], "DC:Cooling"),
    "VOLTAS":       ("Voltas",                     "VOLTAS.NS",     [], "DC:Cooling"),
    "KRN":          ("KRN Heat Exchanger",         "KRN.NS",        [], "DC:Cooling"),
    "HONAUT":       ("Honeywell Automation India", "HONAUT.NS",     [], "DC:BMS"),

    # === Oil / Gas / Hydrogen ===
    "GAIL":         ("GAIL India",                 "GAIL.NS",       [], "Energy:Gas"),
    "IGL":          ("Indraprastha Gas",           "IGL.NS",        [], "Energy:Gas"),
    "MGL":          ("Mahanagar Gas",              "MGL.NS",        [], "Energy:Gas"),
    "GUJGASLTD":    ("Gujarat Gas",                "GUJGASLTD.NS",  [], "Energy:Gas"),
    "PETRONET":     ("Petronet LNG",               "PETRONET.NS",   [], "Energy:LNG"),
    "ONGC":         ("Oil & Natural Gas Corp",     "ONGC.NS",       [], "Energy:Upstream"),
    "OIL":          ("Oil India",                  "OIL.NS",        [], "Energy:Upstream"),
    "BPCL":         ("Bharat Petroleum",           "BPCL.NS",       [], "Energy:OMC"),
    "IOC":          ("Indian Oil Corp",            "IOC.NS",        [], "Energy:OMC"),

    # === Construction / EPC / T&D ===
    "NCC":          ("NCC Limited",                "NCC.NS",        [], "Const:EPC"),
    "KPIL":         ("Kalpataru Projects Intl",    "KPIL.NS",       [], "Const:T&D"),
    "KEC":          ("KEC International",          "KEC.NS",        [], "Const:T&D"),
    "SKIPPER":      ("Skipper",                    "SKIPPER.NS",    [], "Const:Towers"),

    # === Cloud / GPU / AI Compute (added from AI&DC Quant smallcase) ===
    "E2E":          ("E2E Networks",               "E2E.NS",        [], "Cloud:GPU"),
    "NETWEB":       ("Netweb Technologies",        "NETWEB.NS",     [], "Cloud:AIServer"),
    "BBOX":         ("Black Box Limited",          "BBOX.NS",       [], "DC:Building"),
    "RAILTEL":      ("RailTel Corp",               "RAILTEL.NS",    [], "DC:Connectivity"),
    "AMBER":        ("Amber Enterprises",          "AMBER.NS",      [], "DC:Cooling-EMS"),
    "CYIENTDLM":    ("Cyient DLM",                 "CYIENTDLM.NS",  [], "Semi:EMS"),

    # === IT Services (added from Niveshaay TechStack: Software/Data/Cyber) ===
    "PERSISTENT":   ("Persistent Systems",         "PERSISTENT.NS", [], "SW:IT-Svcs"),
    "COFORGE":      ("Coforge",                    "COFORGE.NS",    [], "SW:IT-Svcs"),
    "MPHASIS":      ("Mphasis",                    "MPHASIS.NS",    [], "SW:IT-Svcs"),
    "LTIM":         ("LTIMindtree",                "LTIM.NS",       [], "SW:IT-Svcs"),
    "KPITTECH":     ("KPIT Technologies",          "KPITTECH.NS",   [], "SW:ER&D"),
    "LTTS":         ("L&T Technology Services",    "LTTS.NS",       [], "SW:ER&D"),
    "TATATECH":     ("Tata Technologies",          "TATATECH.NS",   [], "SW:ER&D"),
    "BSOFT":        ("Birlasoft",                  "BSOFT.NS",      [], "SW:IT-Svcs"),
    "CYIENT":       ("Cyient",                     "CYIENT.NS",     [], "SW:ER&D"),
    "SONATSOFTW":   ("Sonata Software",            "SONATSOFTW.NS", [], "SW:IT-Svcs"),

    # === Software Products / SaaS / Cyber ===
    "NEWGEN":       ("Newgen Software",            "NEWGEN.NS",     [], "SW:Product"),
    "TANLA":        ("Tanla Platforms",            "TANLA.NS",      [], "SW:Product"),
    "AFFLE":        ("Affle India",                "AFFLE.NS",      [], "SW:Product"),
    "RATEGAIN":     ("Rategain Travel Tech",       "RATEGAIN.NS",   [], "SW:Product"),
    "HAPPSTMNDS":   ("Happiest Minds",             "HAPPSTMNDS.NS", [], "SW:Product"),
    "ZENTEC":       ("Zen Technologies",           "ZENTEC.NS",     [], "SW:Defence"),
    "QUICKHEAL":    ("Quick Heal Technologies",    "QUICKHEAL.NS",  [], "SW:Cyber"),

    # === Platforms / Consumer Internet (Niveshaay layer 3) ===
    "ETERNAL":      ("Eternal (ex-Zomato)",        "ETERNAL.NS",    [], "Platform:Consumer"),
    "NYKAA":        ("FSN E-Commerce (Nykaa)",     "NYKAA.NS",      [], "Platform:Consumer"),
    "SWIGGY":       ("Swiggy",                     "SWIGGY.NS",     [], "Platform:Consumer"),
    "INDIAMART":    ("IndiaMART InterMesh",        "INDIAMART.NS",  [], "Platform:B2B"),
    "NAUKRI":       ("Info Edge (Naukri)",         "NAUKRI.NS",     [], "Platform:B2B"),

    # === Fintech + Public Rails (Niveshaay layer 4) ===
    "PAYTM":        ("One97 / Paytm",              "PAYTM.NS",      [], "Fintech:Payments"),
    "POLICYBZR":    ("PB Fintech (Policybazaar)",  "POLICYBZR.NS",  [], "Fintech:Insure"),
    "CDSL":         ("Central Depository Svcs",    "CDSL.NS",       [], "Fintech:Infra"),
    "CAMS":         ("Computer Age Mgmt Svcs",     "CAMS.NS",       [], "Fintech:Infra"),
    "KFINTECH":     ("KFin Technologies",          "KFINTECH.NS",   [], "Fintech:Infra"),
    "BSE":          ("BSE Limited",                "BSE.NS",        [], "Fintech:Infra"),
    "MCX":          ("Multi Commodity Exchange",   "MCX.NS",        [], "Fintech:Infra"),
    "ANGELONE":     ("Angel One",                  "ANGELONE.NS",   [], "Fintech:Broker"),
    "PROTEAN":      ("Protean eGov Tech",          "PROTEAN.NS",    [], "Fintech:Infra"),

    # === Miners & Metals ===
    "HINDZINC":     ("Hindustan Zinc",             "HINDZINC.NS",   [], "Mining:Zinc-Ag"),
    "VEDL":         ("Vedanta",                    "VEDL.NS",       [], "Mining:Diversified"),
    "NMDC":         ("NMDC",                       "NMDC.NS",       [], "Mining:IronOre"),
    "COALINDIA":    ("Coal India",                 "COALINDIA.NS",  [], "Mining:Coal"),
    "JSWSTEEL":     ("JSW Steel",                  "JSWSTEEL.NS",   [], "Mining:Steel"),
    "TATASTEEL":    ("Tata Steel",                 "TATASTEEL.NS",  [], "Mining:Steel"),
    "JINDALSTEL":   ("Jindal Steel & Power",       "JINDALSTEL.NS", [], "Mining:Steel"),
    "SAIL":         ("Steel Authority of India",   "SAIL.NS",       [], "Mining:Steel"),
    "HINDALCO":     ("Hindalco (Aluminium)",       "HINDALCO.NS",   [], "Mining:Aluminium"),
    "NATIONALUM":   ("National Aluminium (NALCO)", "NATIONALUM.NS", [], "Mining:Aluminium"),
    "MOIL":         ("MOIL (Manganese)",           "MOIL.NS",       [], "Mining:Manganese"),
    "GMDC":         ("Gujarat Mineral Dev Corp",   "GMDC.NS",       [], "Mining:Lignite"),
    "JSL":          ("Jindal Stainless",           "JSL.NS",        [], "Mining:Steel"),
    "JINDALSAW":    ("Jindal Saw",                 "JINDALSAW.NS",  [], "Mining:Pipes"),
    "GRAPHITE":     ("Graphite India",             "GRAPHITE.NS",   [], "Mining:Graphite"),
    "HEG":          ("HEG Ltd (Graphite)",         "HEG.NS",        [], "Mining:Graphite"),
    "RATNAMANI":    ("Ratnamani Metals",           "RATNAMANI.NS",  [], "Mining:Pipes"),
    "WELCORP":      ("Welspun Corp",               "WELCORP.NS",    [], "Mining:Pipes"),
    "GPIL":         ("Godawari Power & Ispat",     "GPIL.NS",       [], "Mining:Steel"),
    "MAITHANALL":   ("Maithan Alloys",             "MAITHANALL.NS", [], "Mining:Ferro"),

    # === Cement (capex/infra adjacency) ===
    "ULTRACEMCO":   ("UltraTech Cement",           "ULTRACEMCO.NS", [], "Cement"),
    "AMBUJACEM":    ("Ambuja Cements",             "AMBUJACEM.NS",  [], "Cement"),
    "ACC":          ("ACC",                        "ACC.NS",        [], "Cement"),
    "SHREECEM":     ("Shree Cement",               "SHREECEM.NS",   [], "Cement"),
    "DALBHARAT":    ("Dalmia Bharat",              "DALBHARAT.NS",  [], "Cement"),

    # === Safe-Haven / Hedge ETFs (gold, silver, liquid debt, broad market) ===
    # The loop discovers these as defensive when no positive momentum names exist
    "GOLDBEES":     ("Nippon Gold BeES",           "GOLDBEES.NS",   [], "SafeHaven:Gold"),
    "SETFGOLD":     ("SBI Gold ETF",               "SETFGOLD.NS",   [], "SafeHaven:Gold"),
    "GOLDIETF":     ("ICICI Gold ETF",             "GOLDIETF.NS",   [], "SafeHaven:Gold"),
    "SILVERBEES":   ("Nippon Silver BeES",         "SILVERBEES.NS", [], "SafeHaven:Silver"),
    # SILVERIETF dropped — duplicate of SILVERBEES (same underlying), keep older Nippon
    "LIQUIDBEES":   ("Nippon Liquid BeES",         "LIQUIDBEES.NS", [], "SafeHaven:Cash"),
    "NIFTYBEES":    ("Nippon Nifty 50 BeES",       "NIFTYBEES.NS",  [], "Index:Nifty50"),
    "JUNIORBEES":   ("Nippon Nifty Next 50 BeES",  "JUNIORBEES.NS", [], "Index:Next50"),

    # === Factor ETFs (orthogonal-to-momentum smart-beta exposure) ===
    "MOM50":        ("Nifty 500 Momentum 50",      "MOM50.NS",      [], "Factor:Momentum"),
    "MOM100":       ("Motilal Momentum 100",       "MOM100.NS",     [], "Factor:Momentum"),
    "MOMOMENTUM":   ("Motilal Momentum ETF",       "MOMOMENTUM.NS", [], "Factor:Momentum"),
    "ALPHA":        ("Alpha ETF",                  "ALPHA.NS",      [], "Factor:Alpha"),
    "ALPHAETF":     ("Nippon Alpha ETF",           "ALPHAETF.NS",   [], "Factor:Alpha"),
    "QUAL30IETF":   ("ICICI Quality 30",           "QUAL30IETF.NS", [], "Factor:Quality"),
    "SBIETFQLTY":   ("SBI Quality ETF",            "SBIETFQLTY.NS", [], "Factor:Quality"),
    "MONQ50":       ("Motilal Quality 50",         "MONQ50.NS",     [], "Factor:Quality"),
    "MIDQ50ADD":    ("Motilal Midcap Quality 50",  "MIDQ50ADD.NS",  [], "Factor:Quality"),
    "MOVALUE":      ("Motilal Value ETF",          "MOVALUE.NS",    [], "Factor:Value"),
    "NV20IETF":     ("ICICI Nifty Value 20",       "NV20IETF.NS",   [], "Factor:Value"),
    "NV20BEES":     ("Nippon Value 20 BeES",       "NV20BEES.NS",   [], "Factor:Value"),
    "LOWVOLIETF":   ("ICICI Low Vol 30",           "LOWVOLIETF.NS", [], "Factor:LowVol"),
    "EQUAL50ADD":   ("Motilal Equal Weight 50",    "EQUAL50ADD.NS", [], "Factor:EqWt"),

    # === Cap-tier ETFs (broad market exposure) ===
    "NIF100BEES":   ("Nippon Nifty 100 BeES",      "NIF100BEES.NS", [], "Index:Nifty100"),
    "NIF100IETF":   ("ICICI Nifty 100",            "NIF100IETF.NS", [], "Index:Nifty100"),
    "MONIFTY500":   ("Motilal Nifty 500",          "MONIFTY500.NS", [], "Index:Nifty500"),
    "MIDCAP":       ("Motilal Midcap 100",         "MIDCAP.NS",     [], "Cap:Mid"),
    "MIDCAPIETF":   ("ICICI Midcap 150",           "MIDCAPIETF.NS", [], "Cap:Mid"),
    "SMALLCAP":     ("Motilal Smallcap ETF",       "SMALLCAP.NS",   [], "Cap:Small"),
    "MOSMALL250":   ("Motilal Smallcap 250",       "MOSMALL250.NS", [], "Cap:Small"),

    # === Sector ETFs (NIFTYBANK + others) ===
    "BANKBEES":     ("Bank Nifty BeES",            "BANKBEES.NS",   [], "Sector:Bank"),
    "PSUBNKBEES":   ("PSU Bank BeES",              "PSUBNKBEES.NS", [], "Sector:PSUBank"),
    "ITBEES":       ("IT Sector BeES",             "ITBEES.NS",     [], "Sector:IT"),
    "PHARMABEES":   ("Pharma BeES",                "PHARMABEES.NS", [], "Sector:Pharma"),
    "MOHEALTH":     ("Motilal Healthcare",         "MOHEALTH.NS",   [], "Sector:Health"),
    "INFRABEES":    ("Infra BeES",                 "INFRABEES.NS",  [], "Sector:Infra"),
    "CPSEETF":      ("CPSE ETF (PSU basket)",      "CPSEETF.NS",    [], "Sector:PSU"),
    "CONSUMBEES":   ("Consumption BeES",           "CONSUMBEES.NS", [], "Sector:Consumption"),
    "FMCGIETF":     ("ICICI FMCG ETF",             "FMCGIETF.NS",   [], "Sector:FMCG"),
    "AUTOBEES":     ("Auto Sector BeES",           "AUTOBEES.NS",   [], "Sector:Auto"),
    "MODEFENCE":    ("Motilal Defence ETF",        "MODEFENCE.NS",  [], "Sector:Defence"),
    "MAKEINDIA":    ("Make in India ETF",          "MAKEINDIA.NS",  [], "Sector:MakeInIndia"),
    "MOREALTY":     ("Motilal Realty ETF",         "MOREALTY.NS",   [], "Sector:Realty"),

    # === Debt / Bond ETFs ===
    "SETF10GILT":   ("SBI 10Y Gilt ETF",           "SETF10GILT.NS", [], "Debt:Gilt"),
    "MOGSEC":       ("Motilal G-Sec ETF",          "MOGSEC.NS",     [], "Debt:GSec"),
    "EBBETF0430":   ("Bharat Bond 2030",           "EBBETF0430.NS", [], "Debt:BharatBond"),
    "EBBETF0433":   ("Bharat Bond 2033",           "EBBETF0433.NS", [], "Debt:BharatBond"),

    # === Commodity broad ===
    "COMMOIETF":    ("Nippon Commodity ETF",       "COMMOIETF.NS",  [], "Commodity:Broad"),

    # === REIT / InvIT (real assets) ===
    "EMBASSY":      ("Embassy Office Parks REIT",  "EMBASSY.NS",    [], "Real:REIT"),
    "MINDSPACE":    ("Mindspace REIT",             "MINDSPACE.NS",  [], "Real:REIT"),
}


def by_theme(theme_prefix: str) -> list[str]:
    """Return tickers whose theme starts with the given prefix (e.g., 'Cable', 'Power')."""
    return [k for k, v in AI_INFRA_UNIVERSE.items() if v[3].startswith(theme_prefix)]


def themes() -> dict[str, list[str]]:
    """Group tickers by theme."""
    groups: dict[str, list[str]] = {}
    for key, (_, _, _, theme) in AI_INFRA_UNIVERSE.items():
        groups.setdefault(theme, []).append(key)
    return groups


if __name__ == "__main__":
    print(f"AI-Infra India Universe — {len(AI_INFRA_UNIVERSE)} tickers")
    print("=" * 70)
    for theme, keys in sorted(themes().items()):
        print(f"\n[{theme}] {len(keys)}")
        for k in keys:
            print(f"  {k:14s} {AI_INFRA_UNIVERSE[k][0]}")
