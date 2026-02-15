"""Seed script — loads sample internal documents for demo / testing.

Usage (from project root):
  docker compose exec backend python -m app.seed_data

Or standalone:
  python -m app.seed_data
"""

from __future__ import annotations

import asyncio
import logging

import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:8000/api/v1"
TENANT_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"  # Aura Wellness (seeded in init.sql)
HEADERS = {"X-Tenant-Id": TENANT_ID, "Content-Type": "application/json"}

# ── Sample internal documents ────────────────────────────

SAMPLE_DOCUMENTS = [
    {
        "title": "Employee Leave Policy",
        "doc_type": "markdown",
        "content": """# Employee Leave Policy

## Annual Leave
All full-time employees are entitled to 20 days of paid annual leave per calendar year.
Part-time employees receive leave on a pro-rata basis.

Leave must be requested at least 2 weeks in advance for periods longer than 3 consecutive days.
For shorter periods, 48 hours notice is appreciated.

## Sick Leave
Employees receive 10 days of paid sick leave per year.
A medical certificate is required for absences exceeding 3 consecutive days.

Unused sick leave does not carry over to the next year.

## Parental Leave
Primary caregivers are entitled to 16 weeks of paid parental leave.
Secondary caregivers receive 4 weeks of paid leave.
Both must be taken within the first 12 months following the birth or adoption.

## Public Holidays
The company observes 11 public holidays per year.
If a public holiday falls on a weekend, the following Monday is observed.

## Leave Approval Process
1. Submit leave request via the HR portal
2. Direct manager approval required
3. HR confirmation within 2 business days
4. For team-wide absences, department head approval needed

## Contact
For leave-related questions, contact hr@aurawellness.com or ext. 2100.
""",
    },
    {
        "title": "IT Security Guidelines",
        "doc_type": "markdown",
        "content": """# IT Security Guidelines

## Password Policy
- Minimum 12 characters
- Must include uppercase, lowercase, numbers, and special characters
- Passwords must be changed every 90 days
- Do not reuse the last 5 passwords
- Never share passwords via email or chat

## Two-Factor Authentication (2FA)
2FA is mandatory for:
- Email access
- VPN connections
- Cloud service dashboards
- HR and Finance systems

Use the company-approved authenticator app (Google Authenticator or Microsoft Authenticator).

## Data Classification
- **Public**: Marketing materials, blog posts
- **Internal**: Meeting notes, project plans
- **Confidential**: Financial data, HR records, customer PII
- **Restricted**: Encryption keys, access credentials

## Remote Work Security
- Always use the company VPN when accessing internal systems
- Do not use public Wi-Fi without VPN
- Lock your screen when stepping away
- Do not store company data on personal devices without encryption

## Incident Reporting
Report security incidents immediately to security@aurawellness.com or call ext. 9999.
Include: what happened, when, what systems were affected, and any actions taken.

## Software Installation
Only install software approved by IT. Submit requests via the IT Service Desk portal.
Unapproved software will be flagged and may be removed automatically.
""",
    },
    {
        "title": "Onboarding Checklist for New Employees",
        "doc_type": "markdown",
        "content": """# Onboarding Checklist

## Before Day 1
- [ ] Sign employment contract
- [ ] Complete tax forms (W-4 or equivalent)
- [ ] Set up direct deposit
- [ ] Review employee handbook
- [ ] Complete background check

## Day 1
- [ ] Receive laptop and credentials
- [ ] Set up email and Slack
- [ ] Complete IT security training (mandatory)
- [ ] Meet your buddy/mentor
- [ ] Tour the office (or virtual tour for remote)
- [ ] Lunch with team

## Week 1
- [ ] Complete compliance training modules
- [ ] Set up development environment (engineering)
- [ ] Review team OKRs and current sprint
- [ ] 1:1 with direct manager — expectations & goals
- [ ] Access all required systems and tools

## Month 1
- [ ] Complete all mandatory training
- [ ] First project assignment
- [ ] 30-day check-in with manager
- [ ] Provide onboarding feedback

## Systems Access
New employees receive access to:
- Google Workspace (email, calendar, drive)
- Slack
- Jira / Linear (project management)
- GitHub (engineering)
- Figma (design)
- HR Portal (leave, expenses)

Access requests are managed through the IT Service Desk.
Contact: onboarding@aurawellness.com
""",
    },
    {
        "title": "Expense Reimbursement Policy",
        "doc_type": "markdown",
        "content": """# Expense Reimbursement Policy

## Eligible Expenses
- Business travel (flights, hotels, ground transport)
- Client meals and entertainment (pre-approved)
- Conference and training fees
- Office supplies for remote workers (up to $500/year)
- Mobile phone bill (50% reimbursement for roles requiring it)

## Submission Process
1. Collect receipts for all expenses over $25
2. Submit via the Expense Portal within 30 days
3. Include: date, amount, category, business justification
4. Attach photo/scan of receipt
5. Manager approval required for all submissions

## Approval Limits
- Under $100: Direct manager
- $100 - $1,000: Department head
- Over $1,000: VP + Finance approval

## Travel Policy
- Book flights at least 14 days in advance (economy class for domestic)
- Hotel: up to $200/night (exceptions require VP approval)
- Meals: up to $75/day while travelling
- Ride-sharing preferred over rental cars for urban travel

## Reimbursement Timeline
Approved expenses are reimbursed within 10 business days via direct deposit.

## Non-Reimbursable
- Personal entertainment
- Alcohol (unless part of approved client entertainment)
- First-class travel (without VP exception)
- Gym memberships (covered under wellness benefit separately)

## Contact
expenses@aurawellness.com or ext. 2200
""",
    },
    {
        "title": "Company Wellness Benefits",
        "doc_type": "markdown",
        "content": """# Wellness Benefits Program

## Overview
At Aura Wellness, employee wellbeing is our top priority. We offer a comprehensive
wellness benefits package to all full-time employees.

## Physical Wellness
- **Gym Membership**: $100/month reimbursement for gym or fitness classes
- **Annual Health Screening**: Free comprehensive health check-up
- **Ergonomic Equipment**: Up to $500 for home office ergonomic setup
- **Walking Meetings**: Encouraged for 1:1s and informal discussions

## Mental Health
- **EAP (Employee Assistance Program)**: 8 free counselling sessions per year
- **Mental Health Days**: 3 additional days off per year (no questions asked)
- **Meditation App**: Free Headspace subscription for all employees
- **Quiet Hours**: No meetings before 10am on Wednesdays

## Financial Wellness
- **401(k) Match**: Company matches up to 5% of salary
- **Financial Planning**: Free quarterly sessions with a financial advisor
- **Student Loan Assistance**: $200/month towards student loan payments

## Work-Life Balance
- **Flexible Hours**: Core hours 10am-3pm, flex outside
- **Remote Work**: Hybrid model — 2 days office minimum
- **Sabbatical**: 4 weeks paid after 5 years of service
- **No-Meeting Fridays**: Reserved for deep work

## Enrollment
Benefits begin on your start date. Enroll through the HR Portal.
Annual open enrollment period: November 1–30.

## Contact
wellness@aurawellness.com or ext. 2300
""",
    },
]


async def seed():
    """Load all sample documents via the API."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Verify service is up
        try:
            resp = await client.get(f"http://localhost:8000/health")
            resp.raise_for_status()
            logger.info("Backend is healthy: %s", resp.json())
        except Exception as e:
            logger.error("Backend not reachable: %s", e)
            logger.info("Make sure the backend is running (docker compose up)")
            return

        # Ingest documents
        for doc in SAMPLE_DOCUMENTS:
            logger.info("Ingesting: %s", doc["title"])
            resp = await client.post(
                f"{BASE_URL}/documents",
                json=doc,
                headers=HEADERS,
            )
            if resp.status_code == 201:
                data = resp.json()
                logger.info(
                    "  ✓ id=%s chunks=%d",
                    data["document_id"],
                    data["chunk_count"],
                )
            else:
                logger.error("  ✗ %d: %s", resp.status_code, resp.text)

        logger.info("Seed complete! Try asking a question:")
        logger.info(
            "  curl -X POST http://localhost:8000/api/v1/ask "
            '-H "Content-Type: application/json" '
            '-H "X-Tenant-Id: %s" '
            '-d \'{"question": "How many days of annual leave do I get?"}\'',
            TENANT_ID,
        )


if __name__ == "__main__":
    asyncio.run(seed())
