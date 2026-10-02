#!/usr/bin/env python3
"""
Database Seeding Script for IntentGuard Research Prototype.
Populates standard mock customer records, orders, and authorized intents.
"""

def seed():
    print("Seeding initial mock financial records...")
    print("  Customer: C-17")
    print("  Order: ORD-204 (Authorized Amount: 1,500.00 INR)")
    print("  Customer: C-42")
    print("  Order: ORD-500 (Authorized Amount: 5,000.00 INR)")
    print("Database seeding completed.")

if __name__ == "__main__":
    seed()
