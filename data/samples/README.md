# Sample data

- `dienstleistungsvertrag.txt` – a **fictional** German service contract with a few
  deliberately problematic clauses (§ 2 Abs. 3, § 4 Abs. 2, § 5 Abs. 2) and fake
  contact data, so you can test retrieval, contract review and PII redaction.

For real public legal text, download statutes from the official German federal
portal <https://www.gesetze-im-internet.de> (e.g. BGB §§ 305–310, BDSG) and
drop the `.txt`/`.pdf` files here or upload them with `scripts/seed_minio.py`.
Official statutes are not protected by copyright in Germany (§ 5 UrhG).
