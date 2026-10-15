"""
Billing — the Teacher-to-Madar commercial relationship: plans, subscriptions,
trials, billing periods, and payment-provider integration (ADR-014).

This is distinct from `financials`, which tracks the Student-to-Teacher
educational fee (MonthlyPayment) and is never repurposed as commercial
billing. Billing owns its own persistence and provider boundary (ADR-009,
ADR-015); `financials` is untouched by this module.
"""
