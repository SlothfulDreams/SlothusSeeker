from src.bot.embeds import create_company_list_embed


def test_company_list_embed_paginates_companies():
    companies = [
        {"id": index, "company_name": f"company-{index}"}
        for index in range(1, 13)
    ]

    first_page = create_company_list_embed(companies, page=0, per_page=10)
    second_page = create_company_list_embed(companies, page=1, per_page=10)

    assert "`01`  `#1`  **company-1**" in first_page.description
    assert "`10`  `#10`  **company-10**" in first_page.description
    assert "company-11" not in first_page.description
    assert "`11`  `#11`  **company-11**" in second_page.description
    assert first_page.fields[0].value == "12"
    assert first_page.fields[1].value == "1/2"
