# Administrator and staff guide

For custodians, heads of department, facility managers and administrators. Everything here
happens in the staff console at **`/manage/`** (the **Manage** section of the left rail, or
**Manage** in the phone tab bar). You only see the sections your role allows; see
[roles.md](roles.md) for the full matrix. For booking as a person, see the
[user quick-start](guide-user.md).

## Signing in and MFA

Facility managers and administrators sign in with a password **and** a six-digit code from an
authenticator app (Google Authenticator, Microsoft Authenticator, Authy, 1Password and similar).

1. Sign in with your VID or username and password.
2. **First time:** the next page shows a QR code and a setup key. Scan it in your authenticator
   app and enter the six-digit code it shows. You are now enrolled.
3. **Every time after that:** enter the current code from the app.

Good to know:

- Each code works once. If it says the code was already used, wait for the next one.
- Five wrong attempts, passwords and codes together, pause sign-in for 15 minutes. The
  message does not say an account is paused, so that it never confirms an account exists;
  if a colleague cannot sign in after several tries, ask them to wait 15 minutes.
- If your role changes to one that needs MFA while you are signed in, you are signed out and
  asked to sign in again with a code.
- `/django-admin/` uses exactly the same sign-in. Use it only for break-glass data fixes;
  everything routine is in the console.

## The console home

`/manage/` opens on your desk: what needs you now (requests waiting for your approval,
unacknowledged breakdowns, low stock, people paused for no-shows) and what is in use on your
resources today. Counts on the rail items (**Approvals**, **Upkeep**, **Stock**) are the same
numbers.

## Daily work

### Approvals

**Manage → Approvals** lists the steps you may decide, oldest start time first.

- **Approve** confirms the step. If it was the last step, the booking is confirmed and the
  person gets their QR pass.
- **Reject** needs a reason, which the person sees. The slot is released at once.
- A request whose start time passes before anyone decides expires on its own and frees the slot.
- You never see, and cannot decide, requests you made or that are for you. Those go to
  another approver; a facility manager or administrator can decide any step.

### Live booking board

**Manage → Board** shows today on every resource you manage: what is in use, checked in,
waiting for check-in, or free. It refreshes itself. Use it at the start of a session to see
who should be in a room.

### No-shows and booking pauses

A confirmed booking that is not checked in within the grace period is released automatically
and recorded as a **no-show**. Repeated no-shows climb the **restriction ladder** (see
[Policies](#policies)), which can pause a person's booking for some days.

**No-shows** (linked from the console home; facility managers and administrators also find it
under **Setup**) lists recent no-shows on resources you manage and anyone currently paused.

- **Forgive** a no-show when there was a good reason (the room was locked, the person was
  unwell). A reason is required and recorded. If the person no longer qualifies for their
  pause, the pause is lifted too.
- **Lift** a pause directly when needed.
- You cannot forgive your own no-show or lift your own pause.

### Upkeep: breakdowns and maintenance

**Manage → Upkeep** has two parts.

**Breakdown reports.** Anyone can report a problem from a resource's page.

- **Minor** and **Major** reports alert the custodians and leave the resource bookable.
- **Critical** means "nobody should use this". When a custodian (or anyone who manages the
  resource) files it, the resource goes **out of service** at once and the next 24 hours are
  blocked for repair. When anyone else files it, the custodians get an urgent alert and the
  report shows **Unconfirmed, still in service**. Check it, then press **Take out of service**
  to confirm, or simply resolve it if it was not critical.
- **Acknowledge** tells the reporter someone is on it. **Resolve** needs a note on what was
  done; the resource returns to service when no confirmed critical report remains.

**Maintenance windows.** Use **Schedule maintenance** to block a resource for planned work.

1. Pick the resource, the time and what is being done.
2. The preview lists every booking the window would cancel. Timetabled classes are never
   displaced: a window that overlaps a class is refused, so move the class first.
3. Confirm. Displaced people are told, with alternatives.

Windows move from *scheduled* to *in progress* to *completed* on their own. **Complete early**
hands the rest of the time back; **Cancel** frees all of it.

### Stock

**Manage → Stock** lists the accessories (returned after use, such as HDMI cables or tripods)
and consumables (used up, such as whiteboard markers) that people can request with a booking.

- Items are reserved when a booking is made, issued at check-in and returned at check-out.
- **Restock** adds units. Items at or below their reorder level are flagged, and their
  custodians get a low-stock alert.

### Insights

**Manage → Insights** (`/insights/`) shows utilisation for your department (heads of
department) or the whole campus (facility managers, administrators): utilisation by resource,
type, department and block, the **idle-capacity ranking** (expensive equipment nobody uses),
a weekly heat map, no-show rates, demand against supply, approval turnaround, maintenance
downtime and departmental quota consumption.

Every section has a **CSV** export of the rows behind it. Figures come from nightly snapshots,
so today's activity appears tomorrow.

## Resources

**Manage → Resources** lists the resources you manage.

- **Edit** a resource to change its name, capacity, location, features, attributes, photos
  and custodians. Photos are checked and re-encoded on upload (PNG, JPEG or WebP, up to 4 MB).
- **Out of service** needs a reason, which people see on the resource page.
- **Door QR** prints the code for the resource's door. Scanning it with the in-app scanner
  checks in whoever has the current booking.
- Facility managers and administrators can **add** resources and **import** many at once
  from CSV. The import previews every row and imports nothing if any row is wrong.

CSV import columns (`code`, `name`, `type_code` and `capacity` are required):

```
code,name,type_code,building_code,capacity,floor,room,department_code,features,description
```

## Setup

**Manage → Setup** is the hub for configuration. Its cards depend on your role.

### Policies

**Setup → Policies** holds the booking rules. They are data, so a change applies to the next
booking without a deploy ([ADR 0008](adr/0008-data-driven-rules-and-workflows.md)). Campus and
type rules are set by facility managers and administrators; heads of department manage their
department's quotas.

**How precedence works.** This is the part most worth understanding.

| Rule | Set at | Which one applies |
|---|---|---|
| **Booking policy**: slot size, minimum and maximum duration, notice (lead time), how far ahead, check-in required, check-in opens N minutes before, grace period, enforce capacity | campus, resource type, or single resource | The **most specific wins**: resource, then type, then campus, then the built-in default (30-minute slots, 30 minutes to 3 hours, 30 days ahead, check-in from 15 minutes before with 15 minutes' grace) |
| **Opening hours** | campus, type, or resource | The most specific scope that has **any** hours set wins, for the whole week. If nothing is set, Monday to Saturday 08:00 to 20:00 |
| **Blackouts** (holidays, exams, events, restricted periods) | campus, type, or resource | **All** blackouts that overlap apply; each can exempt roles (for example, exams exempt faculty) |
| **Quotas** (hours and/or number of bookings per day, week or month) | a role, or a department | A **role** quota applies to each person with that role separately. A **department** quota is one shared allowance for every booking made for that department's members |
| **Restriction ladder** | campus | Each tier says "N unforgiven no-shows within D days pauses booking for P days" (P = 0 is a warning only). The highest tier reached applies |

When a request breaks a rule, the person is told which rule in a sentence (for example,
"Equipment needs at least 1 hour notice"), so check the rule text if people report surprises.

### Approval workflows

**Setup → Workflows** decides which bookings need approval and who approves them.

A workflow applies to a single resource, a resource type, or everything, and can be narrowed
by **requester role**, **minimum attendees** and **minimum duration**. When a booking matches
more than one workflow:

1. The most specific wins: resource, then type, then everything.
2. Among equally specific workflows, the higher **priority** wins.
3. A workflow with no steps and no auto-approve is ignored.
4. If nothing matches, the booking is confirmed instantly.

Each workflow either **auto-approves** (confirmed at once, with a trail) or has ordered
**steps**. A step names who approves: the resource's custodian, the head of the owning
department, a facility manager, an administrator, or a named person. Steps run in order; a
rejection at any step ends the request.

Use **Who approves this?** in the builder to test a resource, role, attendee count and
duration and see which workflow matches and why. Changes apply to the next booking; requests
already in progress keep their chain.

### Timetable

**Setup → Timetable** imports the published class timetable (P13) so class time is never
offered for booking ([ADR 0003](adr/0003-exclusion-constraints-and-unified-ledger.md)).

1. Choose the term (or add one with its start and end dates).
2. Upload the CSV. Columns:

   ```
   room_code,day,start,end,course_code,course_title,section,faculty,kind
   ```

   `room_code`, `day`, `start`, `end` and `course_code` are required; a sample file is linked
   on the page.
3. **Check** lists every bad row (unknown room, bad time, clash inside the file) and stages
   nothing until the file is clean.
4. **Stage** saves a draft and shows what it would do, including bookings it would cancel.
5. **Publish** applies it in one step: class sessions block their rooms, colliding bookings
   are cancelled with notice and alternatives, and the previous version is retired. If any
   class would overlap maintenance, nothing is published.

Republishing a corrected timetable replaces the old one atomically. **Download** exports any
version as CSV.

### Users and roles

**Setup → Users** lists everyone. Administrators can change roles and deactivate or
reactivate accounts; other staff see the list read-only.

- Role changes take effect immediately and are audited ([roles.md](roles.md#changing-someones-role)).
- Deactivating stops sign-in but keeps bookings and history; nothing is deleted.
- The last active administrator cannot be demoted or deactivated, and nobody can deactivate
  themselves.

### MFA and locked accounts

- **Locked out after failed attempts:** sign-in resumes on its own after 15 minutes.
- **Lost authenticator:** there are no recovery codes yet. An administrator with database
  access clears the person's enrolment, and they enrol again at their next sign-in:

  ```sql
  UPDATE accounts_user SET mfa_enabled = false, mfa_secret = '', mfa_last_step = NULL
  WHERE username = '<username>';
  ```

  Record why in the incident log. A console action for this is planned
  ([known issues](known-issues.md#security-and-privacy), SEC-R1).

### Audit log

**Setup → Audit log** (facility managers, administrators) lists every privileged action: who,
what, on which record, before and after, when, and from which address. Filter by person,
action, record type and date, and export to CSV. The log is append-only: the database refuses changes and
deletions ([ADR 0012](adr/0012-append-only-audit-trigger.md)).

### Operations

**Setup → Operations** (`/manage/ops/`, facility managers and administrators) shows the health
checks, the Celery mode, and each background sweep: when it last ran, what it changed, and
whether it has stalled. **Run now** runs a sweep immediately, for example the no-show sweep
when you want a released slot to show at once. The [runbook](runbook.md#auto-release-has-stalled)
explains what to do when a sweep stalls.

## Demo mode

With `DEMO_MODE=1` the sign-in page offers one-click demo personas, which skip MFA. It is off
by default and must stay off anywhere real people sign in ([environment.md](environment.md)).
