# Feature wishlist

## Wants

How do I lock personal transactions? Auto lock when they go into the ledger maybe?

- can't filter by personal in the ledger either.

Transformation of RBC CSVs

- Chequing ones could benefit from combining the two desciption fields
  - statements have overlapping start and end dates(eg: Jul 1 to Aug 1, the Aug 1 to Sept 1) - Monthly fee and Loan Credit appear on first day of next month and are at the start of the new statement (end of biz day I guess). This causes issues with reconcilliation - I have to move these one day later to have them fall into the right reconcilliation period.
- MC statements have values flipped (negative / positive)
- I could build my checks into this too (account balance verifications)

## For consideration

- change "personal" shortcut to q?
- can't split an invoice to personal and company
- some amazon invoices are one file, two invoices
- could the AI auto link receipts to transactions?
- auto allocate line of credit transfers in Michelle LTD during CSV upload

## Issues

- receipt filename should go in notes if possible

# MichelleCo process

- Import from bank statements
- THEN upload receipts - match those which have a transaction in the bank up with existing transactions
- Reimbursements dryden for others
  - ideally we don't send receipts to the same place - admin@footcarebymichelle.ca should get ALL of the business transactions
  - our inbox should get the personal reimbursements (maybe change to reimbursements@footcarebymichelle.ca for these?) - could automate if IMAP
