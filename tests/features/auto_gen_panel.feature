# Auto Gen right-panel — workflow spec
#
# Purpose: lock in the behavior rules for the "Auto Gen / Build next week's
# schedule" tab in frontend/src/components/schedule/auto-gen-tab.tsx before
# any implementation changes.
#
# Vocabulary
#   Pool           — the Set<employee_id> selected via checkboxes in the UI.
#                    Represents "who the supervisor wants invited on the next
#                    Submit." Pool membership is INDEPENDENT of invite status.
#   Entry          — a single scheduled shift for one employee in one week,
#                    with its own confirmation_status.
#   Invite status  — confirmation_status on an entry: UNSENT, PENDING,
#                    ACCEPTED, DECLINED, REPLACED.
#   Pending reply  — an entry whose status is PENDING (invite sent, awaiting
#                    a response; a demo countdown is running).
#   Submit         — POST /schedule/autogen-submit. Generates entries for
#                    employees in pool who have no entries yet this week and
#                    sends confirmations for them. preserve_pending=true
#                    leaves existing PENDING entries untouched.

Feature: Auto Gen right-panel workflow
  As a staffing supervisor building next week's schedule, I want to manage a
  pool of employees and their confirmation replies from one panel, without
  being blocked by in-flight pending replies and without hidden side-effects
  when I change pool membership.

  Background:
    Given the active staff pool shows 214 employees
    And the current week has no confirmation entries yet

  # --------------------------------------------------------------------
  # Rule 1 — Pool and invite status are separate concepts
  # --------------------------------------------------------------------
  Rule: Pool membership and invite status are independent

    Scenario: Checkbox reflects pool membership, not invite status
      Given "Ahmad Ibrahim" has a PENDING entry for this week
      When I look at his row
      Then the checkbox shows whether he is in the pool
      And the colored dot shows his most-actionable entry status
      And the row caption distinguishes "in pool" from "pending reply"

    Scenario: Unchecking someone with pending invites does not cancel them
      Given "Aisha Johnson" is in the pool
      And she has 3 PENDING entries for this week
      When I uncheck her row
      Then her PENDING entries remain PENDING
      And a row-level note reads "Removed from pool — 3 pending invites still open. Use Remove from pool to cancel them."
      And no mutation is fired to the backend

    Scenario: Re-checking a previously unchecked employee does not resend invites
      Given "Aisha Johnson" has 3 PENDING entries
      And I unchecked her earlier in this session
      When I re-check her row
      Then her pool membership is restored
      And her PENDING entries remain PENDING
      And no new invites are generated until the next Submit

    Scenario: Remove from pool cancels pending/unsent entries for that employee
      Given "Brian Clark" has 2 PENDING entries and 1 ACCEPTED entry
      When I click "Remove from pool" on his row
      Then his 2 PENDING entries move to REPLACED
      And his 1 ACCEPTED entry is left untouched
      And he is removed from the pool

  # --------------------------------------------------------------------
  # Rule 2 — Submit is never deadlocked by pending replies
  # --------------------------------------------------------------------
  Rule: Submit only generates entries for pool members who have no entries yet

    Scenario: Submit is enabled while pending replies exist
      Given 214 employees are in the pool
      And 112 entries for this week are PENDING
      Then the Submit button is enabled
      And the footer reads "214 in pool · 112 pending replies (won't be re-sent)"

    Scenario: Submit only invites newly added pool members
      Given 10 employees have PENDING entries already
      And I add 3 additional employees to the pool
      When I click Submit
      Then the backend receives employee_pool = all 13 employees
      And preserve_pending = true
      And exactly 3 employees receive new invites
      And the existing 10 PENDING entries are untouched

    Scenario: Submit with empty pool is disabled
      Given 0 employees are in the pool
      Then the Submit button is disabled
      And the footer reads "0 in pool"

    Scenario: Submit during an in-flight submit is disabled
      Given a Submit request is in flight
      Then the Submit button is disabled
      And its label reads "Submitting…"

    Scenario: Submit after some pool members were unchecked mid-flow
      Given "David Brown" has 5 PENDING entries
      And I uncheck "David Brown"
      And "Fatima Ali" is newly added to the pool
      When I click Submit
      Then the backend receives employee_pool excluding David Brown
      And David Brown's 5 PENDING entries remain PENDING (they are not cancelled by Submit)
      And Fatima Ali receives new invites

  # --------------------------------------------------------------------
  # Rule 3 — Countdown timer visibility
  # --------------------------------------------------------------------
  Rule: The countdown only shows on rows with an actionable PENDING entry

    Scenario: PENDING row shows a live countdown
      Given "Carlos Mendez" has a PENDING entry with 12 seconds remaining
      Then his row shows "12s"
      And Accept and Decline buttons are visible

    Scenario: DECLINED row hides the countdown
      Given "Diana Wilson" has a DECLINED entry
      Then her row does not show any countdown
      And a "Remove from pool" button is visible
      And no Accept/Decline buttons are shown

    Scenario: ACCEPTED row hides the countdown
      Given "Grace Park" has only ACCEPTED entries
      Then her row does not show any countdown
      And no Accept/Decline/Remove buttons are shown

    Scenario: UNSENT row hides the countdown
      Given "Ryan Lee" has an UNSENT entry (submit has not yet dispatched it)
      Then his row does not show any countdown
      And no Accept/Decline buttons are shown

    Scenario: Mixed-status employee — countdown only if at least one entry is PENDING
      Given "Ahmad Ibrahim" has 1 ACCEPTED, 1 DECLINED, and 1 PENDING entry
      Then his row shows the countdown for the PENDING entry
      And Accept/Decline act on the PENDING entry only

    Scenario: Countdown resets when a new PENDING entry arrives for the same row
      Given "Aisha Johnson" has a PENDING entry with 4 seconds remaining
      When a Submit creates a second PENDING entry for her
      Then the row continues to show a single countdown
      And the countdown reflects the oldest-still-pending entry
      # Rationale: we only act on one pending entry per row at a time; the
      # user resolves them sequentially via Accept/Decline.

  # --------------------------------------------------------------------
  # Rule 4 — Respond actions (Accept / Decline / Timeout)
  # --------------------------------------------------------------------
  Rule: Accept, Decline, and Timeout each transition one entry

    Scenario: Accept transitions PENDING to ACCEPTED
      Given "Carlos Mendez" has a PENDING entry
      When I click Accept on his row
      Then POST /schedule/confirmations/{entry_id}/respond is called with {"response": "ACCEPTED"}
      And on success his row's dot becomes green
      And no replacement dialog is opened

    Scenario: Decline triggers the replacement dialog
      Given "Brian Clark" has a PENDING entry
      When I click Decline on his row
      Then POST /schedule/confirmations/{entry_id}/respond is called with {"response": "DECLINED"}
      And on success the response body includes a "replacement" object
      And the parent page opens the ReplacementDialog with that payload

    Scenario: Decline without a replacement available
      Given "Brian Clark" has a PENDING entry
      And the server returns a DECLINED response with replacement = null
      When I click Decline
      Then his row's dot becomes red
      And a "Remove from pool" button appears
      And no ReplacementDialog is opened

    Scenario: Respond buttons are disabled while a mutation is in flight
      Given any respond or remove mutation is in flight
      Then Accept, Decline, and Remove from pool buttons are disabled on every row
      # Rationale: prevents double-fires across rapid clicks.

    Scenario: Respond error is shown at the row that caused it
      Given "Carlos Mendez" clicks Accept
      And the server returns 500
      Then an inline error appears under his row (not at panel level)
      And a Retry button is shown on that row
      And other rows remain interactive

  # --------------------------------------------------------------------
  # Rule 5 — Timeout handling (bulk, not per-row)
  # --------------------------------------------------------------------
  Rule: Timed-out invites are resolved by one bulk call, not N per-row calls

    Scenario: A single bulk timeout sweep covers all expired pending entries
      Given 40 employees each have 2 PENDING entries
      And all 80 countdowns reach 0 at the same moment
      When the timeout sweep fires
      Then exactly 1 request is sent to POST /schedule/confirmations/timeout-sweep
      And the request body lists the 80 expired entry_ids
      And no per-row TIMEOUT respond calls are made

    Scenario: Timeout sweep runs on a single shared ticker
      Given the panel is open with pending entries
      Then there is exactly one interval/timer driving all countdowns
      # Rationale: the current implementation spawns one useCountdown per
      # row, which fires N independent mutations on expiry. We want one
      # shared ticker that computes remaining seconds per entry from a
      # single "now" value.

    Scenario: A row's countdown reaching 0 marks the entry as expired locally but does not mutate
      Given "Aisha Johnson" has a PENDING entry with 1 second remaining
      When the shared ticker advances past its deadline
      Then her row's dot becomes neutral (expired, awaiting sweep)
      And her row shows "expired — syncing…"
      And the bulk timeout sweep (next tick) includes her entry_id

    Scenario: Closing the panel does not fire timeouts
      Given the panel has pending entries with non-zero remaining time
      When the user navigates away from the tab
      Then no timeout mutations are fired
      And countdowns resume from their server-side sent_at when the panel reopens
      # Rationale: countdown is derived from sent_at + timeout_seconds, not
      # from an in-memory start time, so tab switches do not reset it.

  # --------------------------------------------------------------------
  # Rule 6 — Summary badges and footer accuracy
  # --------------------------------------------------------------------
  Rule: Summary counts are per-entry; pool count is per-employee; labels reflect this

    Scenario: Summary badges count entries
      Given this week has 112 PENDING, 0 ACCEPTED, 7 DECLINED, 0 REPLACED entries
      Then the badges read: "112 pending", "0 accepted", "7 declined", "0 replaced"
      And each badge's tooltip reads "entries, not employees"

    Scenario: Footer explains the pool-vs-pending distinction
      Given 214 employees are in the pool
      And 112 entries are PENDING
      Then the footer reads: "214 in pool · 112 pending replies (won't be re-sent)"
      And hovering "won't be re-sent" shows "Submit only invites pool members who have no entries this week."

    Scenario: Zero pending reads cleanly
      Given 214 employees are in the pool
      And 0 entries are PENDING
      Then the footer reads: "214 in pool"
      And no pending-replies clause is shown

  # --------------------------------------------------------------------
  # Rule 7 — Row ordering and status orb priority
  # --------------------------------------------------------------------
  Rule: Row orb reflects the most actionable entry

    Scenario Outline: Orb color follows status priority
      Given an employee has entries with statuses <statuses>
      Then the row's orb shows the color for <dominant>

      Examples:
        | statuses                                | dominant |
        | [DECLINED, PENDING, ACCEPTED]           | DECLINED |
        | [PENDING, ACCEPTED]                     | PENDING  |
        | [UNSENT, ACCEPTED]                      | UNSENT   |
        | [ACCEPTED, REPLACED]                    | ACCEPTED |
        | [REPLACED]                              | REPLACED |

    Scenario: Employees with no entries this week show a neutral orb
      Given "Ryan Lee" has no entries for this week
      Then his row's orb is neutral/slate
      And his row shows no Accept/Decline/Remove controls
      And his checkbox still toggles pool membership

  # --------------------------------------------------------------------
  # Rule 8 — Initial pool derivation (first render)
  # --------------------------------------------------------------------
  Rule: On first render, the pool is derived from whoever already has non-REPLACED entries

    Scenario: Returning to the tab mid-flow reflects current entries
      Given 10 employees already have PENDING entries for this week
      And the supervisor has not touched any checkbox yet
      When the panel mounts
      Then exactly those 10 employees are checked
      And the footer reads "10 in pool · N pending replies (won't be re-sent)"

    Scenario: Once the supervisor touches any checkbox, the pool becomes manual
      Given the derived pool is 10 employees
      When I uncheck one of them
      Then the pool becomes manual with 9 employees
      And later server updates to entries do not change the pool
      # Rationale: we must not clobber the supervisor's in-progress edits
      # when a websocket push / refetch arrives.

  # --------------------------------------------------------------------
  # Rule 9 — Finalize stop condition
  # --------------------------------------------------------------------
  Rule: Finalize warns when no available candidates remain

    Scenario: Declines exhaust the remaining staffing pool
      Given 1 PENDING entry remains for this week
      And that employee is the only person left in the pool
      When I reopen that entry and click Finalize
      Then the backend returns candidate_exhausted = true
      And the panel shows "Stop condition reached"
      And the warning says "No available candidates remain"
      And the warning says "Please review the staffing pool or scheduling conditions"
      And Generate is disabled until the pool changes

  # --------------------------------------------------------------------
  # Rule 10 — Accessibility / safety invariants
  # --------------------------------------------------------------------
  Rule: The panel must be safe to click through quickly

    Scenario: Each row's controls have accessible labels
      Then each checkbox has an aria-label "Include <name> in pool"
      And each Accept/Decline/Remove button has an aria-label naming the employee and action
      And the countdown text is announced politely (aria-live=polite) only on the row it belongs to

    Scenario: Rapid double-click on Accept does not fire two mutations
      Given "Carlos Mendez" has a PENDING entry
      When I double-click Accept within 200ms
      Then exactly one POST /respond call is fired
      # Implementation: button disabled on mutation start; or dedupe by entry_id.
