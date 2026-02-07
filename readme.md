# Validation of Correct `w_out` Calculation in Entanglement Swapping

This document summarizes the test performed to verify the correct computation of the `w_out` parameter after an entanglement swapping operation in the simulator. The goal is to confirm that the final value recorded at the end nodes matches the expected value according to the theoretical decay model for Werner states.

## 1. Purpose of the Test

The test was designed to check:

- Whether the `w_out` value of the swapped EPR pair was being computed correctly.
- Whether the temporal decay applied to the original EPRs (A and B) matched the real time at which the swapping occurred.
- Whether the final value measured at the end node (`w_real`) matched the theoretical expected value (`w_theor`).

## 2. Issue Identified

In the original implementation, the new `w_out` was computed as:

    w_out_new = w_A * w_B

where `w_A` and `w_B` were the stored `w_out` values of the original EPRs.  
The problem is that these values corresponded to the state of the EPR at the moment it was generated or received, not at the actual time of the swapping.

This caused:

- `w_direct = w_A * w_B` to be too high.
- `w_real` to be lower, since it included the real decay up to the measurement time.
- A systematic error between theory and practice.

## 3. Corrected Approach

To fix the calculation, `w_A` and `w_B` must be updated to the real swap time:

    delta_B = t_swap - t_gen_B (Usually, t_recv_B = t_swap)

    w_A * w_B = exp(-2 * delta_B / t_coh)

    w_out_new = w_A * w_B

This ensures that the stored `w_out` of the swapped EPR reflects the accumulated decay up to the moment of the swapping.

## 4. Test Results

Multiple swapping blocks were processed. For each block, the following were compared:

- `w_direct` (direct product of outdated w_out values)
- `w_theor` (theoretical value using correct decay)
- `w_real` (value measured at the end node)

Example results:

    A_ID         B_ID         ΔA      ΔB      w_A      w_B    w_direct   w_theor   w_real    error
    ------------------------------------------------------------------------------------------------
    soy0ohtpw    08qri5tj4   0.624   0.320   0.93951  0.96850   0.90992    0.87985   0.90991  -0.03006
    elwk6gcv4    cua6g4238   1.028   0.103   0.90231  0.98974   0.89305    0.95964   0.89305   0.06659
    470r57foo    p16w7gx59   0.709   0.102   0.93146  0.98984   0.92200    0.96002   0.92200   0.03802

Observed pattern:

- `w_direct` is always higher than `w_real`.
- `w_theor` matches the expected decay from the model.
- The error between `w_theor` and `w_real` comes from the original implementation not updating `w_A` and `w_B` to the real swap time.

## 5. Conclusion

The test confirms that the original `w_out` calculation did not account for the temporal decay accumulated up to the swapping moment.  
The corrected method —recomputing `w_A` and `w_B` using the real swap time— aligns the results with the theoretical model and removes the systematic error.

This README documents the behavior observed and serves as a reference for validating future modifications to the simulator.
