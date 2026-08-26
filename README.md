# Cardiff Bin Collections

An unofficial Home Assistant integration for Cardiff bin collection dates.
Enter your postcode, pick your address, and the next collections will appear as
date sensors you can use in dashboards and automations.

## Features

- Next and following collection dates, including the bins due.
- Separate date sensors for each waste type.
- A local cache, so dates stay available if Cardiff's service is temporarily
  down.
- One staggered refresh each Sunday, with retries if it fails.
- A rate-limited **Refresh now** button.
- Address changes through **Settings → Devices & services → Reconfigure**.

Postcodes are not case-sensitive, and the space is optional. For example,
`cf99 9zz` and `CF999ZZ` are treated as the same postcode.

## Install with HACS

1. In HACS, open **Custom repositories** from the three-dot menu.
2. Add `https://github.com/chitminthu/cardiff-bin-collections` as an
   **Integration**.
3. Find **Cardiff Bin Collections** in HACS and download it.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration** and search for
   **Cardiff Bin Collections**.

## Entities

Collection sensors use `YYYY-MM-DD` date states. Dates that have passed are
ignored automatically, so **Next collection** always points to today or a future
date. If only one future date is cached, **Following collection** is `unknown`
until the next schedule update.

| Entity | What it shows |
| --- | --- |
| Next collection | The earliest collection that has not passed |
| Following collection | The next collection after that, when available |
| General, Recycling, Food, Garden and Glass | The next date for that waste type |
| Hygiene and Christmas tree | Less common waste types; disabled by default |
| Refresh now | Requests fresh data, limited to once per hour |

The two combined collection sensors include `day`, `bins`, `bin_ids`,
`collection_types` and `bin_details`. Each `bin_details` item contains `type`,
`bin_id`, `collection_type` and `image_url`. Individual waste sensors expose the
same details for their bin where relevant.

Collection sensors also expose `data_source`, `last_successful_refresh`,
`next_scheduled_refresh`, `cache_age_hours` and `last_refresh_error`. These are
useful in dashboards and automations for checking whether live or cached data is
being shown. Entity IDs depend on your Home Assistant naming, so copy them from
the entity settings rather than relying on an example ID.

## Dashboard card

There is an optional example card in
[`examples/upcoming-bin-day-card.yaml`](examples/upcoming-bin-day-card.yaml).
It uses `custom:button-card` and shows both upcoming collections with the bin
pictures supplied by Cardiff Council.

The card is completely optional. All collection dates remain normal Home
Assistant entities, so you can build your own cards and automations instead.

## Automation

Date sensor states use the standard `YYYY-MM-DD` format. An example reminder is
available in
[`examples/bin-reminder-automation.yaml`](examples/bin-reminder-automation.yaml).
Replace the example entity ID and notification action with your own.

## Refreshes and stored data

The integration refreshes on Sunday between 05:00 and 08:59 local time. The
exact time is spread between properties to avoid everyone contacting Cardiff
Council together. Failed updates are retried later on Sunday and Monday while
the last successful data stays available from Home Assistant's local storage.

Your postcode is sent to Cardiff Council to find matching addresses. The chosen
UPRN is then used to request collection dates. Nothing is sent to this project's
maintainer, and there is no analytics or tracking.

Bin pictures are loaded from URLs returned by Cardiff Council and are not kept
in this repository. This project is not affiliated with or endorsed by Cardiff
Council, and its web service may change without notice.

## Related project

[`TomBrien/cardiffwaste-ha`](https://github.com/TomBrien/cardiffwaste-ha) is an
earlier integration for Cardiff waste collections. This project is a separate
implementation with its own entity model, caching and refresh schedule.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
pytest
ruff check .
```

## Licence

MIT. See [LICENSE](LICENSE).
