/-
  PlayFinder v1 — formal invariants (Lean 4)
  These are the safety properties the app relies on. They are simple enough
  to prove without any Android dependency.
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

/-- Push is active iff now < expiry. -/
def pushActive (now expiry : Nat) : Bool := now < expiry

theorem pushActive_false_after_expiry (now : Nat) :
    pushActive (grantExpiry now 1) (grantExpiry now 1) = false := by
  simp [pushActive]

/-- Watchlist contains at most five venues (spec constraint). -/
def atMostFive (s : List Nat) : Prop := s.length ≤ 5

theorem atMostFive_tail (s : List Nat) (h : atMostFive s) :
    atMostFive s.tail := by
  unfold atMostFive at h
  cases s <;> simp_all
  omega

/-- Available colour is green iff count > 0. -/
def isGreen (available : Nat) : Bool := available > 0

theorem isGreen_zero : isGreen 0 = false := by simp [isGreen]
theorem isGreen_positive (n : Nat) (h : n > 0) : isGreen n = true := by
  simp [isGreen, h]

end PlayFinder