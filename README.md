### Masar MCE Assets

Asset management customizations for MCE on ERPNext v15 (built on top of `masar_mce`).
A Word version of this guide, written as a release email, is in
[`documents/MCE Assets Manual & Checklist.pdf`](documents/MCE Assets Manual & Checklist.pdf).
The app has two features:

1. **IT Asset Role Matrix**: an IT asset workflow on Purchase Receipt, Stock Entry and Asset Movement,
   controlled by roles.
2. **Location Asset Quantity Limit**: a maximum number of asset units per Asset Category in each Location.

Every rule is enforced on the server (form, REST API, whitelisted methods, background jobs, data
import). The form scripts only mirror the rules in the UI.

---

### 1. IT Asset Role Matrix

#### Who it applies to

Configure the roles in **IT Asset Role Matrix Settings** (single DocType, System Manager only):

| Table | Meaning |
|---|---|
| **IT Asset Roles** (Function 1) | Users with any of these roles must follow the IT asset workflow. Seeded with `IT Warehouse`. |
| **Ignore IT Asset Role Matrix Roles** (Function 2) | Users with any of these roles are exempt, even if they also have an IT asset role. Empty by default. |

Each user falls into one of three groups:

| Group | Condition | Behaviour |
|---|---|---|
| **IT user** | Has an IT asset role and no ignore role | All restrictions below apply. |
| **Exempt user** | Has an ignore role | No restrictions; may use the IT naming series and sees the IT fields. |
| **Other user** | Neither | Standard behaviour; cannot use the IT naming series. |

- The ignore roles always win. Being exempt only skips these IT rules; ERPNext permissions and validations still apply.
- `Administrator` has every role, so it is exempt as soon as any ignore role is configured.
- `All` and `Guest` cannot be used, and a role cannot be in both tables.
- Role changes take effect on the next page load in the browser and immediately on the server.

#### Purchase Receipt

| Rule | IT user | Exempt user | Other user |
|---|---|---|---|
| Naming series `IT-PRE-.YYYY.-` | Always used, field read-only | Optional | Not available |
| **Normal Cycle** (`custom_normal_cycle`) | Checked by default (can be unchecked) | Standard | Standard |
| Warranty Expiry, Invoice Date, Invoice No, Referral Decision No, Approval Letter Date, Approval Letter No | Shown | Shown | Unchanged (shown only for the IT series) |
| **Auto Submit Assets** (`custom_auto_submit_assets`) | Available | Available | Available |

**Serial numbers.** On submit of a receipt that uses `IT-PRE-.YYYY.-`, every fixed asset row whose item
auto-creates *one Asset per unit* (Auto Create Assets on, Is Grouped Asset off) needs serial
numbers in **Serial Numbers IT** (`custom_serial_numbers_it`):

- one serial number per line (commas also accepted), exactly one per unit; the quantity must be a whole number;
- a serial number cannot repeat inside the receipt, or be used by another Asset of the same item;
- after submit, each created Asset gets its serial number in **Serial No** (`Asset.custom_serial_no`), in creation order.

Grouped asset items, non-asset items and receipts with other naming series are not checked.

**Auto Submit Assets.** When the box is checked, submitting the receipt queues a background job (queue `long`)
that runs after the receipt is committed, as the user who submitted it. For each draft Asset created by the receipt, the job:

1. reads the first Finance Book row of the Asset Category;
2. sets *Available for Use Date* = *Purchase Date* and checks *Calculate Depreciation*;
3. sets the finance book row (method, number of depreciations, frequency, start date = purchase date);
4. saves and submits the Asset.

Each Asset is committed on its own. If one fails (for example its category has no Finance Book),
only that Asset is undone; the error goes to the **Error Log** and the job continues with the others.
A comment on the receipt lists how many were submitted, failed or skipped. Running the job again only picks up
Assets that are still drafts, and it updates the existing finance book row instead of adding another.
The submitting user needs permission to submit Assets.

#### Stock Entry

| Rule | IT user | Exempt user | Other user |
|---|---|---|---|
| Naming series `IT-STE-.YYYY.-` | Always used, field read-only | Optional | Not available |
| Stock Entry Type | Only `سند اخراج` | Any | Any |

#### Asset Movement

| Rule | IT user | Exempt user | Other user |
|---|---|---|---|
| Purpose | Only `Transfer` or `Issue` | Any | Any |
| Approval Letter No, Approval Letter Date, Default Target Location | Mandatory | Optional | Optional |
| Row **Target Location** | Read-only, always set from *Default Target Location* | Standard | Standard |

For IT users the **Default Target Location** (`custom_default_target_location`) controls the movement:
changing it updates every row, new rows inherit it, and the server sets it on every row before
ERPNext validates the movement. Source locations are not changed.

The Receipt movement that ERPNext creates when an Asset is submitted is not checked against these rules.

---

### 2. Location Asset Quantity Limit

A Location can limit how many asset units of each Asset Category it holds, in the
**Asset Category Limits** table on the Location (`Maximum Quantity`, 0 = none allowed).
Categories without a row are unlimited.

- Quantities are asset units (`Asset.asset_quantity`), not the number of Asset documents.
  Cancelled, sold, scrapped and capitalized Assets are not counted.
- The limit is checked when units arrive in a Location: Purchase Receipt / Purchase Invoice (with Update Stock)
  submit, Asset save, Asset Movement submit, and Asset Movement cancel (which returns Assets to their old location).
- Moving assets out of a Location is always allowed, even when it is over its limit.
- Concurrent transactions are serialized per Location, so two users cannot both pass the check against the same stock.

---

### Technical reference

| Area | Files |
|---|---|
| Role matrix, naming series | `masar_mce_assets/it_asset_role_matrix.py`, DocType `it_asset_role_matrix_settings` |
| Purchase Receipt (serials, auto submit trigger) | `masar_mce_assets/it_asset_purchase_receipt.py`, `custom/purchase_receipt/purchase_receipt.py` |
| Auto submit background job | `masar_mce_assets/it_asset_auto_submit.py` |
| Stock Entry | `custom/stock_entry/stock_entry.py` |
| Asset Movement | `custom/asset_movement/it_asset.py`, `custom/asset_movement/asset_movement.py`, `custom/asset/asset.py` |
| Location limit | `masar_mce_assets/asset_location_limit.py`, `custom/location`, DocType `location_asset_category_limit` |
| Form scripts | `public/js/it_asset_role_matrix.js`, `purchase_receipt.js`, `stock_entry.js`, `asset_movement.js` |
| Custom fields | `fixtures/custom_field.json` (module `Masar MCE Assets`) |
| Tests | `tests/test_it_asset_role_matrix.py`, `tests/test_asset_location_limit.py` |

**Deployment notes**

- `bench --site <site> migrate` creates the settings DocType, seeds the IT asset role (patch
  `v1_0.set_default_it_asset_role_matrix`), syncs the custom fields and adds the IT naming series to the
  Purchase Receipt and Stock Entry naming series options.
- The naming series are added again after every migrate, because `masar_mce`'s fixtures restore
  those options without them.
- `masar_mce`'s fixtures also export every Purchase Receipt custom field. When a field in this app's module
  changes, export the fixtures of both apps so they stay identical.
- Run `bench build --app masar_mce_assets` after updating the form scripts.

**Tests**
```bash
bench --site <site> run-tests --app masar_mce_assets --module masar_mce_assets.tests.test_it_asset_role_matrix
```

The tests create their own roles, users, items, categories and locations and roll everything back.
They need a company with a fixed asset account on an Asset Category.
`test_asset_location_limit` also needs an existing submitted fixed asset Purchase Receipt on the site.

### Installation
You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app masar_mce_assets
```

### Contributing
This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:
```bash
cd apps/masar_mce_assets
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:
- ruff
- eslint
- prettier
- pyupgrade
### CI
This app can use GitHub Actions for CI. The following workflows are configured:
- CI: Installs this app and runs unit tests on every push to `develop` branch.
- Linters: Runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.

### License
mit