from api.data_access import FinancialDataProvider

def verify_bgfv():
    print("Connecting to database...")
    db = FinancialDataProvider()
    
    print("\n--- Company Info ---")
    company = db.get_company_info("BGFV")
    if company:
        print(f"Ticker: {company['ticker']}")
        print(f"Name: {company['entity_name']}")
        print(f"Sector: {company['sector']}")
        print(f"Industry: {company['industry']}")
    else:
        print("BGFV not found in company table!")
        return

    print("\n--- Financial Metrics ---")
    # Revenues
    rev = db.get_latest_metric("BGFV", "Revenues")
    if rev:
        print(f"Latest Revenue: ${rev['value']:,.2f} (Filed: {rev['filing_date']})")
    else:
        print("Revenue not found")

    # Assets
    assets = db.get_latest_metric("BGFV", "Assets")
    if assets:
        print(f"Latest Assets: ${assets['value']:,.2f} (Filed: {assets['filing_date']})")
    else:
        print("Assets not found")
        
    # Net Income TTM
    ttm = db.get_latest_ttm("BGFV", "NetIncome_TTM")
    if ttm:
        print(f"Net Income TTM: ${ttm['ttm_value']:,.2f}")
    else:
        print("Net Income TTM not found")

    print("\n--- Corrected Financial Metrics ---")
    # RevenueFromContractWithCustomerExcludingAssessedTax
    rev_tag = "RevenueFromContractWithCustomerExcludingAssessedTax"
    rev = db.get_latest_metric("BGFV", rev_tag)
    if rev:
        print(f"Latest Revenue ({rev_tag}): ${rev['value']:,.2f} (Filed: {rev['filing_date']})")
    
    # Check NetIncomeLoss since TTM logic might depend on NetIncomeLoss
    ni = db.get_latest_metric("BGFV", "NetIncomeLoss")
    if ni:
        print(f"Latest Net Income: ${ni['value']:,.2f} (Filed: {ni['filing_date']})")

if __name__ == "__main__":
    verify_bgfv()
