{
    "name": "Report Myanmar Text",
    "category": "Productivity",
    "summary": "Correct the Myanmar text on PDF reports.",
    "author": "White Star Myanmar education center",
    "company": "White Star Myanmar education center",
    "maintainer": "White Star Myanmar education center",
    "website": "https://www.facebook.com/odooerpdevelopment",
    "license": "LGPL-3",
    "installable": True,
    "auto_install": False,
    "application": False,
    "depends": ["base"],
    "assets": {
        "web.report_assets_common": [
            "/report_myanmar_text_v18/static/src/scss/font.scss",
        ],
        "account_reports.assets_pdf_export": [
            "/report_myanmar_text_v18/static/src/scss/font.scss",
        ]
    }
}
