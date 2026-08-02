# Private procurement-history import

Procurement history is commercial context, not farm identity. It can answer:

- Which village/variety cohorts supplied volume in a month?
- What quantity and weighted purchase rate did a cohort show?
- Where should a manager compare current procurement reality with the active
  crop and mandi context?

It cannot prove a farm's boundary, land right, farmer identity, agronomic
practice, or current field condition.

## Supported source ledger

The manager-only `POST /api/v1/procurement-history/csv` intake recognizes the
historical Fortune-style columns below. The original CSV is processed in memory
and is **not retained**.

```csv
Entry Date,Purchase: Paddy Purchase Number,Farmer Name,Village,Rate Per Qtl,Bag,Paddy Quantity Qtl,PO Name,Variety Type,Supply Bill No. (1st Attempt)
```

Before evidence retention, AGRO CEO drops farmer names, purchase numbers, PO
names, and supply-bill identifiers. It retains a deterministic CSV of only:

```csv
month,village_name,variety_name,purchase_count,quantity_qtl,bag_count,weighted_rate_per_qtl
```

The same named manager reviews and publishes the aggregate batch. It never
creates a farm, farmer, field, payment record, or map pin. The generic CSV
routes cannot access this special-purpose batch.

## How it joins the operating system

Use a reviewed farm/plot manifest for **where a field is**. Use procurement
history for **what the network previously supplied**. They join only at
reviewed administrative context such as village, crop variety, and season—not
through a farmer name or inferred parcel.
