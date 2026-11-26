/-
  PlayFinder v1 — formal invariants (Lean 4)
  These are the safety properties the app relies on. They are simple enough
  to prove without any Android dependency.

  Note: this file is not compiled by CI (no Lean toolchain is pinned in the
  repository), so treat it as a written specification of the invariants
  rather than as a machine-checked proof.
-/

namespace PlayFinder

/-- A slot's availability is a non-negative count. -/
structure Slot where
  available : Nat
  h : available ≥ 0 := by omega

/-- Push grant: granting N weeks moves the expiry strictly into the future. -/
def grantExpiry (now : Nat) (weeks : Nat) : Nat := now + weeks * 7 * 24 * 3600

theorem grantExpiry_future (now weeks : Nat) (h : weeks > 0) :
    grantExpiry now weeks > now := by
  unfold grantExpiry
  omega

/--
Push is active iff the grant is enabled and now is before the expiry.
This mirrors `Watchlist.pushActive` in `alerts/WatchlistStore.kt`.
-/
def pushActive (enabled : Bool) (now expiry : Nat) : Bool :=
  enabled && decide (now < expiry)

theorem pushActive_false_after_expiry (now : Nat) :
    pushActive true (grantExpiry now 1) (grantExpiry now 1) = false := by
  simp [pushActive]

theorem pushActive_false_when_disabled (now expiry : Nat) :
    pushActive false now expiry = false := by
  simp [pushActive]

theorem pushActive_true_before_expiry (now expiry : Nat) (h : now < expiry) :
    pushActive true now expiry = true := by
  simp [pushActive, h]

/-- Watchlist contains at most five venues (spec constraint). -/
def atMostFive (s : List Nat) : Prop := s.length ≤ 5

theorem atMostFive_tail (s : List Nat) (h : atMostFive s) :
    atMostFive s.tail := by
  unfold atMostFive at h
  cases s <;> simp_all
  omega

/--
Availability is "open" iff the count is above zero. The app renders an open
session with the theme's primary container colour and a full session with the
error container colour; there is no green/red pair in the code.
-/
def isOpen (available : Nat) : Bool := available > 0

theorem isOpen_zero : isOpen 0 = false := by simp [isOpen]
theorem isOpen_positive (n : Nat) (h : n > 0) : isOpen n = true := by
  simp [isOpen, h]

end PlayFinder
