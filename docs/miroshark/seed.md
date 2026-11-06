# Launch brief: RAWRS, verified accessible documents for US local governments

## The regulation
- The US Department of Justice ADA Title II rule requires state and local government websites and documents, including PDFs, to meet WCAG 2.1 AA.
- On 20 April 2026 DOJ extended the deadlines by one year: 26 April 2027 for cities and counties serving 50,000+ people, 26 April 2028 for smaller ones and special districts. DOJ said it had overestimated governments' capacity and cited the limits of generative AI for remediation.
- PDFs posted before the deadline are exempt unless people use them to apply for or access a service. New agendas, minutes, budgets, notices and forms must comply.
- The National Federation of the Blind sued in May 2026 to restore the original dates. DOJ says it may revisit the substance of the rule.
- There are 90,837 local governments in the US. Vendors estimate a county has 10,000-50,000 PDFs online; nobody has a neutral count.

## The market today
- Fully automated remediation sells for $0.30 per page (CASO Comply, Accessibility On Demand); $1.80 with AI checks and a "95% compliance score" guarantee; $12+ per page with human review.
- Human remediation services charge $4-25 per page.
- Arizona State University and AWS released a free open-source tool that uses Adobe's auto-tagging API. Hancom released free open-source auto-tagging (OpenDataLoader PDF).
- Many cities have no budget line for this and buy under small-purchase thresholds without a formal tender.

## The new product: RAWRS
- Made by WinVinaya InfoSystems (Bengaluru, India). Its sister foundation trains and places persons with disabilities; reviewers include screen-reader users.
- RAWRS reads scanned and born-digital PDFs, rebuilds headings, reading order, tables, footnotes and image descriptions, and sends anything it is unsure about to a human review queue with evidence.
- Measured on 10 test documents: it decides 81.5% of structure items without a human (median 84.6% per document). How often reviewers keep its decisions unchanged is not yet measured.
- Its main claim: cheap automated tools can pass the standard PDF/UA machine check while the document is unreadable. In a test, two scanned books "passed" with zero characters of readable text: a screen reader would read nothing.
- Proposed prices: $1.50 per page verified-automated (readable text guaranteed, uncertain items flagged); $6 per page human-reviewed; monthly subscription for new documents.
- Free offer: an audit report of a city's website listing which PDFs fail and which "pass" but are unreadable.
- Weaknesses: unknown company, based outside the US, no US government customers yet, no SOC 2, accessible PDF export still being built, slower than fully automated tools.

## The question
Over the next six months, how will US city and county ADA coordinators, clerks, IT directors, procurement officers, disability advocates, remediation agencies and competing vendors react to RAWRS? Will cities of 50,000+ people pay $1.50-$6 per page for verified documents instead of $0.30 automated remediation or doing nothing, before the April 2027 deadline?

## Stakeholders (fictional people and places, invented for this simulation)
- Dana Whitfield, ADA coordinator, City of Harlow Springs (population 140,000). Has 12,000 PDFs online, no remediation budget line, reports to the city attorney.
- Marcus Oyelaran, city clerk, Brennan County (population 310,000). Posts 40 agendas and minutes a month; staff of three; worried about meeting packets.
- Priya Raman, IT director, City of Eastvale (population 85,000). Already pays for a website platform with an accessibility checker; skeptical of new vendors.
- Tom Kessler, procurement officer, Lakemont County (population 220,000). Small-purchase threshold of $50,000; needs a W-9, insurance certificate and a VPAT before any purchase order.
- Gloria Fuentes, city manager, City of Port Alder (population 60,000). Budget is tight; would rather take down old PDFs than pay to fix them.
- Kevin Marsh, councilmember, City of Harlow Springs. Asks why the city should pay a company based in India.
- Renee Holloway, blind screen-reader user and disability advocate in Brennan County. Has filed two DOJ complaints about unreadable county PDFs.
- Samuel Ortiz, attorney at a disability rights legal center. Tracks the NFB lawsuit; warns cities that "passing a checker" is not a defence.
- Linda Cho, owner of a US remediation agency with 15 staff, charges $8 per page; could resell RAWRS white-label or see it as a threat.
- Brian Taft, sales lead at a fully automated remediation vendor selling at $0.30 per page with a compliance-score guarantee.
- Aisha Bello, accessibility lead at a state municipal league, advises 200 member cities on the ADA Title II rule.
- Raj Mehta, founder of RAWRS at WinVinaya InfoSystems, Bengaluru; pitches the free audit report.
