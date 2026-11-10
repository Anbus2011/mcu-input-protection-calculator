# Test changes since the 401-test baseline

The baseline is the suite on branch `bug-fixes` (commit `69564fa`): 401 tests. This file lists every one of those tests that was removed or rewritten on `div-v2`, one line each, with the reason. A parametrised test has one line per case.

| | Tests |
|---|---|
| Baseline | 401 |
| Kept (not listed here) | 260 |
| Rewritten | 47 |
| Removed | 94 |
| Added since | 418 |
| **Suite when this file was written** | **725** |

- **Removed**: nothing tests that thing any more, because the thing itself is gone.
- **Rewritten**: the thing tested was replaced or redefined by the brief (`docs/session2_prompt.md`) or by a later owner decision, and the test now checks what replaced it.
- **Kept**: the test checks the same behaviour as before. It was edited only as far as the new solver API, key names, fixture files and model-dependent numbers required. The last section lists the kept tests whose assertions changed in substance.

Three fields moved rather than disappeared, so their test cases count as kept: `zener.ptot_mw` is now `diode.ptot_mw`, `bw.c_diode_pf` is `diode.capacitance_pf`, and `bw.c_pin_pf` is `mcu.c_pin_pf`.

Four test files were renamed with the modules they test: `test_circuit_model.py` → `test_design_calculation.py`, `test_bandwidth_model.py` → `test_frequency.py`, `test_fixes_model.py` → `test_solver_rules.py`, `test_fixes_app_state.py` → `test_app_state.py`.

The tables below were generated from the two lists of test IDs (baseline and current) and checked: every baseline test is in exactly one of kept, rewritten or removed, and every kept or rewritten test maps to a test that exists now.

## Removed (94)

### `tests/test_bandwidth_model.py` (6)

| Test | Reason |
|---|---|
| `TestRcFilterBasics::test_3db_bandwidth` | The −3 dB bandwidth is no longer calculated (brief: Frequency). |
| `TestRcFilterBasics::test_rise_time` | The 10–90 % rise time is no longer calculated (brief: Frequency). |
| `TestRcFilterBasics::test_analog_conservative` | The conservative analog limit, 1 / (10 τ), is removed (brief: Frequency). |
| `TestFrequencyLimits::test_limiting_factor_identified` | There is no bottleneck name: the four limits became two (brief: Frequency). |
| `TestFrequencyLimits::test_counter_overflow_unsigned` | The counter-overflow limit and its inputs are removed (brief: Frequency). |
| `TestFrequencyLimits::test_counter_overflow_signed` | The counter-overflow limit and its inputs are removed (brief: Frequency). |

### `tests/test_circuit_model.py` (4)

| Test | Reason |
|---|---|
| `TestAdcSampleCycles::test_low_impedance` | `ADC_SAMPLE_THRESHOLDS` and the Min Sample Cycles row are removed: the table did not match DS12983 Rev 5, Table 67 (brief: The checks). |
| `TestAdcSampleCycles::test_mid_impedance` | `ADC_SAMPLE_THRESHOLDS` and the Min Sample Cycles row are removed: the table did not match DS12983 Rev 5, Table 67 (brief: The checks). |
| `TestAdcSampleCycles::test_high_impedance` | `ADC_SAMPLE_THRESHOLDS` and the Min Sample Cycles row are removed: the table did not match DS12983 Rev 5, Table 67 (brief: The checks). |
| `TestAdcSampleCycles::test_boundary_values` | `ADC_SAMPLE_THRESHOLDS` and the Min Sample Cycles row are removed: the table did not match DS12983 Rev 5, Table 67 (brief: The checks). |

### `tests/test_fixes_app_state.py` (19)

| Test | Reason |
|---|---|
| `TestEditsMarkDirty::test_every_field_marks_dirty[zener.vz_nom]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `TestEditsMarkDirty::test_every_field_marks_dirty[zener.vz_min]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `TestEditsMarkDirty::test_every_field_marks_dirty[zener.vz_max]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `TestEditsMarkDirty::test_every_field_marks_dirty[zener.izt_ma]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `TestEditsMarkDirty::test_every_field_marks_dirty[zener.zzt_typ]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `TestEditsMarkDirty::test_every_field_marks_dirty[zener.zzt_max]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `TestEditsMarkDirty::test_every_field_marks_dirty[zener.izk_ma]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `TestEditsMarkDirty::test_every_field_marks_dirty[zener.zzk_typ]` | ZZK is removed with the old Zener model; this field no longer exists. |
| `TestEditsMarkDirty::test_every_field_marks_dirty[zener.zzk_max]` | ZZK is removed with the old Zener model; this field no longer exists. |
| `TestEditsMarkDirty::test_every_field_marks_dirty[mcu.safe_injection_ma]` | The injection estimate and its limit field are removed (owner decision, 2026-11-09). |
| `TestEditsMarkDirty::test_every_field_marks_dirty[bw.f_peripheral_mhz]` | The peripheral clock field is removed (brief: Frequency); the MCU's minimum pulse width replaces it. |
| `TestEditsMarkDirty::test_every_field_marks_dirty[bw.n_samples]` | The N_samples field is removed (brief: Frequency); the MCU's minimum pulse width replaces it. |
| `TestEditsMarkDirty::test_every_field_marks_dirty[bw.counter_bits]` | The counter-overflow limit and its fields are removed (brief: Frequency). |
| `TestEditsMarkDirty::test_every_field_marks_dirty[bw.counter_signed]` | The counter-overflow limit and its fields are removed (brief: Frequency). |
| `TestEditsMarkDirty::test_every_field_marks_dirty[bw.f_read_hz]` | The counter-overflow limit and its fields are removed (brief: Frequency). |
| `TestPresetModified::test_edit_shows_modified_and_saves_custom` | Presets, the preset drop-down and preset tracking are removed (brief: The app). |
| `TestPresetModified::test_unmodified_saves_preset_name` | Presets, the preset drop-down and preset tracking are removed (brief: The app). |
| `TestPresetModified::test_editing_back_restores_preset` | Presets, the preset drop-down and preset tracking are removed (brief: The app). |
| `TestPresetModified::test_old_file_with_edited_values_shows_modified` | Presets, the preset drop-down and preset tracking are removed (brief: The app). |

### `tests/test_fixes_model.py` (7)

| Test | Reason |
|---|---|
| `TestNoDataclassDefaults::test_zzk_is_not_needed` | ZZK is removed with the old Zener model (brief: The solver). |
| `TestNoDataclassDefaults::test_zzk_does_not_change_any_result` | ZZK is removed with the old Zener model (brief: The solver). |
| `TestBandwidthModel::test_effective_is_min_when_all_known` | There is no effective limit: the four limits became two (brief: Frequency). |
| `TestInjectionEstimate::test_node_above_onset_gives_expected_current` | The injection estimate is removed (owner decision, 2026-11-09). |
| `TestInjectionEstimate::test_no_series_resistor_needs_no_tolerance` | The injection estimate is removed (owner decision, 2026-11-09). |
| `TestInjectionEstimate::test_series_resistor_needs_its_tolerance` | The injection estimate is removed (owner decision, 2026-11-09). |
| `TestWorstCasePower::test_rs_worst_peak_inside_tolerance_band` | The "peak at 100 Ω" rule went with the injection estimate; R_s power is now V_node,max² / R_s,min (owner decision, 2026-11-09). |

### `tests/test_ui.py` (58)

| Test | Reason |
|---|---|
| `test_every_input_marks_unsaved_and_recalculates[zener.vz_nom]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_every_input_marks_unsaved_and_recalculates[zener.vz_min]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_every_input_marks_unsaved_and_recalculates[zener.vz_max]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_every_input_marks_unsaved_and_recalculates[zener.izt_ma]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_every_input_marks_unsaved_and_recalculates[zener.zzt_typ]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_every_input_marks_unsaved_and_recalculates[zener.zzt_max]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_every_input_marks_unsaved_and_recalculates[zener.izk_ma]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_every_input_marks_unsaved_and_recalculates[zener.zzk_typ]` | ZZK is removed with the old Zener model; this field no longer exists. |
| `test_every_input_marks_unsaved_and_recalculates[zener.zzk_max]` | ZZK is removed with the old Zener model; this field no longer exists. |
| `test_every_input_marks_unsaved_and_recalculates[mcu.safe_injection_ma]` | The injection estimate and its limit field are removed (owner decision, 2026-11-09). |
| `test_every_input_marks_unsaved_and_recalculates[bw.f_peripheral_mhz]` | The peripheral clock field is removed (brief: Frequency); the MCU's minimum pulse width replaces it. |
| `test_every_input_marks_unsaved_and_recalculates[bw.n_samples]` | The N_samples field is removed (brief: Frequency); the MCU's minimum pulse width replaces it. |
| `test_every_input_marks_unsaved_and_recalculates[bw.counter_bits]` | The counter-overflow limit and its fields are removed (brief: Frequency). |
| `test_every_input_marks_unsaved_and_recalculates[bw.counter_signed]` | The counter-overflow limit and its fields are removed (brief: Frequency). |
| `test_every_input_marks_unsaved_and_recalculates[bw.f_read_hz]` | The counter-overflow limit and its fields are removed (brief: Frequency). |
| `test_blank_zero_unreadable[zener.vz_nom-]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_blank_zero_unreadable[zener.vz_nom-0]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_blank_zero_unreadable[zener.vz_nom-abc]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_blank_zero_unreadable[zener.vz_min-]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_blank_zero_unreadable[zener.vz_min-0]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_blank_zero_unreadable[zener.vz_min-abc]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_blank_zero_unreadable[zener.vz_max-]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_blank_zero_unreadable[zener.vz_max-0]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_blank_zero_unreadable[zener.vz_max-abc]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_blank_zero_unreadable[zener.izt_ma-]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_blank_zero_unreadable[zener.izt_ma-0]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_blank_zero_unreadable[zener.izt_ma-abc]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_blank_zero_unreadable[zener.zzt_typ-]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_blank_zero_unreadable[zener.zzt_typ-0]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_blank_zero_unreadable[zener.zzt_typ-abc]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_blank_zero_unreadable[zener.zzt_max-]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_blank_zero_unreadable[zener.zzt_max-0]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_blank_zero_unreadable[zener.zzt_max-abc]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_blank_zero_unreadable[zener.izk_ma-]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_blank_zero_unreadable[zener.izk_ma-0]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_blank_zero_unreadable[zener.izk_ma-abc]` | The five-number Zener description is replaced by the diode tables; this field no longer exists. |
| `test_blank_zero_unreadable[zener.zzk_typ-]` | ZZK is removed with the old Zener model; this field no longer exists. |
| `test_blank_zero_unreadable[zener.zzk_typ-0]` | ZZK is removed with the old Zener model; this field no longer exists. |
| `test_blank_zero_unreadable[zener.zzk_typ-abc]` | ZZK is removed with the old Zener model; this field no longer exists. |
| `test_blank_zero_unreadable[zener.zzk_max-]` | ZZK is removed with the old Zener model; this field no longer exists. |
| `test_blank_zero_unreadable[zener.zzk_max-0]` | ZZK is removed with the old Zener model; this field no longer exists. |
| `test_blank_zero_unreadable[zener.zzk_max-abc]` | ZZK is removed with the old Zener model; this field no longer exists. |
| `test_blank_zero_unreadable[mcu.safe_injection_ma-]` | The injection estimate and its limit field are removed (owner decision, 2026-11-09). |
| `test_blank_zero_unreadable[mcu.safe_injection_ma-0]` | The injection estimate and its limit field are removed (owner decision, 2026-11-09). |
| `test_blank_zero_unreadable[mcu.safe_injection_ma-abc]` | The injection estimate and its limit field are removed (owner decision, 2026-11-09). |
| `test_blank_zero_unreadable[bw.f_peripheral_mhz-]` | The peripheral clock field is removed (brief: Frequency); the MCU's minimum pulse width replaces it. |
| `test_blank_zero_unreadable[bw.f_peripheral_mhz-0]` | The peripheral clock field is removed (brief: Frequency); the MCU's minimum pulse width replaces it. |
| `test_blank_zero_unreadable[bw.f_peripheral_mhz-abc]` | The peripheral clock field is removed (brief: Frequency); the MCU's minimum pulse width replaces it. |
| `test_blank_zero_unreadable[bw.n_samples-]` | The N_samples field is removed (brief: Frequency); the MCU's minimum pulse width replaces it. |
| `test_blank_zero_unreadable[bw.n_samples-0]` | The N_samples field is removed (brief: Frequency); the MCU's minimum pulse width replaces it. |
| `test_blank_zero_unreadable[bw.n_samples-abc]` | The N_samples field is removed (brief: Frequency); the MCU's minimum pulse width replaces it. |
| `test_blank_zero_unreadable[bw.counter_bits-]` | The counter-overflow limit and its fields are removed (brief: Frequency). |
| `test_blank_zero_unreadable[bw.counter_bits-0]` | The counter-overflow limit and its fields are removed (brief: Frequency). |
| `test_blank_zero_unreadable[bw.counter_bits-abc]` | The counter-overflow limit and its fields are removed (brief: Frequency). |
| `test_blank_zero_unreadable[bw.f_read_hz-]` | The counter-overflow limit and its fields are removed (brief: Frequency). |
| `test_blank_zero_unreadable[bw.f_read_hz-0]` | The counter-overflow limit and its fields are removed (brief: Frequency). |
| `test_blank_zero_unreadable[bw.f_read_hz-abc]` | The counter-overflow limit and its fields are removed (brief: Frequency). |
| `test_zzk_marked_reference_only` | ZZK and its "reference only" note are removed with the old Zener model. |

## Rewritten (47)

### `tests/test_bandwidth_model.py`, now in `tests/test_frequency.py` (6)

| Was | Now | Reason |
|---|---|---|
| `TestThresholdTiming::test_undefined_zone_positive` | `TestEdgeTiming::test_edge_times_positive` | The two "undefined zone" times are replaced by the rising and falling edge times. |
| `TestThresholdTiming::test_rising_formula` | `TestEdgeTiming::test_rising_formula` | New rising-edge formula: from 0 V towards the lowest pin voltage at Logic High, to VIH. |
| `TestThresholdTiming::test_falling_formula` | `TestEdgeTiming::test_falling_formula` | New falling-edge formula: from the highest pin voltage at Max Input towards the highest at Logic Low, to VIL. |
| `TestFrequencyLimits::test_all_limits_positive` | `TestFrequencyLimits::test_both_limits_positive` | Four limits became two: "may work up to" and "reliable up to". |
| `TestFrequencyLimits::test_conservative_less_than_practical` | `TestFrequencyLimits::test_reliable_not_above_may_work` | The two analog limits are removed; the pair compared is now reliable against may work. |
| `TestFrequencyLimits::test_effective_is_minimum` | `TestFrequencyLimits::test_edge_time_is_the_larger_of_the_two` | There is no effective limit; the edge time is the larger of the two edge times. |

### `tests/test_circuit_model.py`, now in `tests/test_design_calculation.py` (8)

| Was | Now | Reason |
|---|---|---|
| `TestZenerVoltage::test_zero_current` | `TestDiodeCurve::test_no_voltage_no_current` | The three-region Zener model (knee factors, IZK, IZT, ZZT) is replaced by the diode tables; the test checks the same region of the table model. |
| `TestZenerVoltage::test_below_knee_current` | `TestDiodeCurve::test_below_the_first_row` | The three-region Zener model (knee factors, IZK, IZT, ZZT) is replaced by the diode tables; the test checks the same region of the table model. |
| `TestZenerVoltage::test_at_knee_current` | `TestDiodeCurve::test_at_a_table_row` | The three-region Zener model (knee factors, IZK, IZT, ZZT) is replaced by the diode tables; the test checks the same region of the table model. |
| `TestZenerVoltage::test_between_knee_and_test` | `TestDiodeCurve::test_between_rows` | The three-region Zener model (knee factors, IZK, IZT, ZZT) is replaced by the diode tables; the test checks the same region of the table model. |
| `TestZenerVoltage::test_at_test_current` | `TestDiodeCurve::test_at_5_ma` | The three-region Zener model (knee factors, IZK, IZT, ZZT) is replaced by the diode tables; the test checks the same region of the table model. |
| `TestZenerVoltage::test_above_test_current` | `TestDiodeCurve::test_above_the_last_row` | The three-region Zener model (knee factors, IZK, IZT, ZZT) is replaced by the diode tables; the test checks the same region of the table model. |
| `TestZenerVoltage::test_worst_case_higher_than_typical` | `TestDiodeCurve::test_maximum_column_conducts_least` | The three-region Zener model (knee factors, IZK, IZT, ZZT) is replaced by the diode tables; the test checks the same region of the table model. |
| `TestFullCalculation::test_plot_data_present` | `TestFullCalculation::test_plot_data_from_app_state_not_from_the_solver` | The solver returns no plot data; AppState sweeps the pin-voltage function (brief: The app). |

### `tests/test_file_io.py` (2)

| Was | Now | Reason |
|---|---|---|
| `TestBackwardsCompatibility::test_load_results_div` | `TestOtherFiles::test_load_example_file` | `results.div` (format 1.0) is gone; a format 2.0 example file is loaded instead. |
| `TestBackwardsCompatibility::test_missing_fields_use_defaults` | `TestOtherFiles::test_blank_values_load_blank_with_one_warning` | In format 2.0 a missing key is a format problem; the test now uses null values, which load blank with one warning. |

### `tests/test_fixes_app_state.py`, now in `tests/test_app_state.py` (17)

| Was | Now | Reason |
|---|---|---|
| `TestBandwidthDerivation::test_tau_resistance_is_parallel_plus_rs` | `TestFrequencyInputs::test_tau_resistance_is_parallel_of_maximums_plus_rs_max` | τ now uses R1, R2 and R_s at their high tolerance (brief: Frequency). |
| `TestBandwidthDerivation::test_rs_zero_still_gives_bandwidth` | `TestFrequencyInputs::test_rs_zero_still_gives_limits` | It opened `results.div` and checked the effective limit and bottleneck; it now opens the Schottky example and checks the two limits. |
| `TestBandwidthDerivation::test_v_high_is_lowest_pin_voltage_at_logic_high_input` | `TestFrequencyInputs::test_high_level_is_lowest_pin_voltage_at_logic_high_input` | "Lowest" is now the lowest of the eight corners, not R1 max / R2 min with the typical Zener (brief: The solver). |
| `TestBandwidthDerivation::test_never_reaches_vih_is_reported_not_replaced` | `TestFrequencyInputs::test_pin_never_reads_high_is_reported_not_replaced` | The effective and counter-overflow limits it checked are gone; it checks the note and that neither of the two limits is given. |
| `TestBandwidthStartingValues::test_c_diode_starting_value_is_datasheet_max` | `TestBandwidthStartingValues::test_margin_factor_starting_value` | C_diode is clamp diode data now, not a starting value; the starting values are C_stray and the margin factor (1.5). |
| `TestBandwidthStartingValues::test_file_without_bandwidth_key_loads_blank` | `TestBandwidthStartingValues::test_blank_bandwidth_values_load_blank` | In format 2.0 the `bandwidth` section must be present; null values in it load blank. |
| `TestNoHiddenDefaults::test_unused_blank_fields_block_nothing` | `TestNoHiddenDefaults::test_labels_and_notes_block_nothing` | ZZK is gone; the fields no result uses are now the part names, type, pin type, sources, notes and "checked" boxes. |
| `TestNoHiddenDefaults::test_blank_vz_min_needed_only_for_worst_power` | `TestNoHiddenDefaults::test_blank_minimum_cell_needed_only_for_worst_case` | VZ min is replaced by the minimum column of the diode tables. |
| `TestRangeChecks::test_vz_order` | `TestRangeChecks::test_row_order_min_typ_max` | VZ min ≤ VZ nom ≤ VZ max became v_min ≤ v_typ ≤ v_max in a table row. |
| `TestRangeChecks::test_izk_below_izt` | `TestRangeChecks::test_currents_ascend` | IZK below IZT became: table currents ascend from row to row. |
| `TestSeriesResistorRules::test_injection_uses_rs_low_tolerance` | `TestSeriesResistorRules::test_rs_power_uses_rs_low_tolerance` | The injection estimate is removed; R_s at its low tolerance is now used for the R_s power, V_node,max² / R_s,min (owner decision, 2026-11-09). |
| `TestLoading::test_one_warning_lists_all_missing` | `TestLoading::test_one_warning_lists_all_blank_values_that_are_needed` | In format 2.0 a missing key is a format problem; the one warning now lists null values that results need. |
| `TestLoading::test_malformed_rejected_and_state_untouched[<lambda>-bandwidth.counter_bits]` | `TestLoading::test_malformed_rejected_and_state_untouched[<lambda>-mcu.adc_bits]` | `bandwidth.counter_bits` no longer exists; the non-whole-number case uses `mcu.adc_bits`. |
| `TestLoading::test_malformed_rejected_and_state_untouched[<lambda>-bandwidth.counter_signed]` | `TestLoading::test_malformed_rejected_and_state_untouched[<lambda>-clamp_diode.checked]` | `bandwidth.counter_signed` no longer exists; the not-true-or-false case uses `clamp_diode.checked`. |
| `TestLoading::test_malformed_rejected_and_state_untouched[<lambda>-zener.preset]` | `TestLoading::test_malformed_rejected_and_state_untouched[<lambda>-clamp_diode.type]` | `zener.preset` no longer exists; the wrong-type case uses `clamp_diode.type`. |
| `TestLoading::test_results_div_still_loads` | `TestLoading::test_format_1_file_is_refused` | Reading `results.div` as format 1.0 is removed: a 1.0 file now gets one clear message and the design on screen is untouched. |
| `TestPresetModified::test_preset_fills_visible_fields` | `TestNoHiddenDefaults::test_no_presets` | Presets are removed; the test now checks there is no preset table, function or key. |

### `tests/test_fixes_model.py`, now in `tests/test_solver_rules.py` (10)

| Was | Now | Reason |
|---|---|---|
| `TestSolverSettling::test_cap_step_rule_unchanged` | `TestSolverSettling::test_no_step_where_the_0_5_ma_rule_stepped` | The 0.5 mA rule and its 0.2 V step are removed; the test checks the curve is continuous at the same input voltage. |
| `TestNoDataclassDefaults::test_params_default_to_none` | `TestNoHiddenDefaults::test_solver_has_no_fallback_values` | The parameter dataclasses are gone (the solver takes a dict); the test checks the solver reads no key with a fallback value. |
| `TestAdcAndThresholds::test_v_high_pin_is_lowest_pin_voltage_at_logic_high` | `TestAdcAndThresholds::test_high_level_is_lowest_pin_voltage_at_logic_high` | "Lowest" is now the lowest of the eight corners, not R1 max / R2 min with the typical Zener (brief: The solver). |
| `TestBandwidthModel::test_v_high_below_vih_blocks_limits_no_fallback` | `TestFrequencyRules::test_pin_never_reads_high_blocks_limits_no_fallback` | The effective limit and its fallback to the counter-overflow limit are gone; the test checks that neither of the two limits is given and the note says why. |
| `TestBandwidthModel::test_effective_needs_every_limit` | `TestFrequencyRules::test_limits_need_every_input` | There is no effective limit; the test checks the two limits need every input. |
| `TestBandwidthModel::test_tau_from_given_resistance` | `TestFrequencyRules::test_tau_from_maximum_resistances` | τ is no longer given a resistance: it uses R1 max ∥ R2 max + R_s max. |
| `TestBandwidthModel::test_rising_formula_with_v_high` | `TestFrequencyRules::test_rising_formula` | New rising-edge formula (0 V to VIH); the VIL-to-VIH "undefined zone" is gone. |
| `TestInjectionEstimate::test_reference_case_is_zero` | `TestNoInjectionEstimate::test_safe_max_is_the_guard` | The injection estimate is removed; the test checks there is none and that Safe Max is the guard (owner decision, 2026-11-09). |
| `TestWorstCasePower::test_hand_checked_rs_worst` | `TestWorstCasePower::test_hand_checked_rs_worst` | R_s worst-case power is now V_node,max² / R_s,min with the pin held at 0 V, with no 100 Ω (owner decision, 2026-11-09). |
| `TestWorstCasePower::test_vz_min_blocks_only_worst_power` | `TestWorstCasePower::test_blank_minimum_column_blocks_only_worst_case` | The low-voltage Zener corner derived from VZ min is replaced by the minimum column of the diode tables. |

### `tests/test_ui.py` (4)

| Was | Now | Reason |
|---|---|---|
| `test_preset_shows_modified` | `test_no_preset_dropdown` | Presets are removed; the test checks the Clamp Diode panel has no part drop-down and fills nothing by itself. |
| `test_results_div_bandwidth_outputs` | `test_example_file_gives_frequency_outputs` | `results.div` and the old bandwidth outputs are gone; the test opens the Schottky example and checks the new outputs. |
| `test_never_reaches_vih_shown_on_tab` | `test_pin_never_reads_high_shown_on_tab` | The effective and counter-overflow cells it checked are gone; it checks the note and that the two limits show no value. |
| `test_injection_row_is_an_estimate_and_zero_for_reference` | `test_no_injection_row_and_safe_max_is_the_guard` | The injection row is removed; the test checks the row, the limit field and the 100 Ω are gone and that Safe Max is the guard (owner decision, 2026-11-09). |

## Kept tests whose assertions changed in substance

These tests still check the same behaviour, but an expected value or an assertion is different. Kept tests that changed only in how they call the solver or name a result are not listed.

### Expected numbers (the diode model changed)

| Test | Change |
|---|---|
| `test_solver_rules.py::TestReferenceCase::test_reference_values` | Typical 3.18 V → 3.02 V; the "worst Zener" 3.43 V became the highest of the corners, 3.24 V. Diode current 2.5 mA unchanged. |
| `test_solver_rules.py::TestReferenceCase::test_reference_displayed_precision` | 3.177 / 3.433 / 3.434 V and 2.51 mA → 3.020 / 3.235 / 3.239 V and 2.53 mA. |
| `test_solver_rules.py::TestSolverSettling::test_low_value_divider_converges` | The closed form was the old model above IZT (28.375 / 2.7 V); it is now the extended last table segment. |
| `test_solver_rules.py::TestWorstCasePower::test_hand_checked_r1_corner` | New hand calculation on the minimum column: 2.8477 V and 74.47 mW (was 2.98659 V and 73.71 mW). The corner is named "diode min" instead of "VZ min". |
| `test_app_state.py::test_reference_case_through_app_state` | The same numbers as `test_reference_values`. |
| `test_ui.py::test_reference_typed_through_widgets` | 3.177 → 3.020 V, 3.433 → 3.235 V, 2.51 → 2.53 mA. It now also types the 13 rows of the reverse table. |
| `test_ui.py::test_new_design_clears_everything`, `test_save_and_reopen` | 3.177 → 3.020 V. |
| `test_ui.py::test_low_value_divider_converges_without_warning` | The expected text was the old closed form; it is now AppState's value, checked to lie between 4 and 5 V. |
| `test_ui.py::test_power_typical_and_worst_shown` | R1 worst-case power 73.7 → 74.5 mW. |
| `test_ui.py::test_two_worst_case_voltages_labelled_apart` | 3.433 / 3.434 V → 3.235 / 3.239 V; the label is "Worst clamp diode (nominal R)". |

### Injection assertions dropped (owner decision, 2026-11-09)

| Test | Change |
|---|---|
| `test_solver_rules.py::TestNoStaleOrFakeResults::test_r1_zero_gives_no_results_not_zeros` | The injection value and status are no longer asserted. |
| `test_app_state.py::TestNoHiddenDefaults::test_blank_vdd_shows_needs_input_but_rest_computes` | "Injection is None" became "the Logic High check needs input". |
| `test_app_state.py::TestSeriesResistorRules::test_no_series_resistor_needs_nothing` (2 cases) | "Injection is 0 mA" became "there is no `power_rs` check". |
| `test_app_state.py::TestSeriesResistorRules::test_rs_rating_and_tol_needed_when_positive` | "Injection is None" is dropped; the `power_rs` status is asserted instead. |
| `test_app_state.py::TestPowerFollowUp::test_reference_typical_and_worst` | "Injection is 0 mA" became "there is no injection check and no injection field". |
| `test_ui.py::test_r1_r2_blank_or_zero_clears_tables_and_plot` (4 cases) | The two injection cells are no longer in the list of cells checked. |
| `test_ui.py::test_rs_row_needs_and_shows_values` | R_s worst-case power 0.0 mW → 106.0 mW and margin 100 % → 58 %: R_s power is now V_node,max² / R_s,min. |
| `test_solver_rules.py::TestWorstCasePower::test_worst_at_least_typical_for_each_part` (case 1), `test_rs_margins_use_rs_rating`, `TestPowerVerdict::test_series_resistor_counts_in_verdict` | The R_s ratings in the fixtures were raised or lowered to suit the new R_s power. |

### Other assertions

| Test | Change |
|---|---|
| `test_solver_rules.py::TestSingleSolver::test_5v_repro_worst_case_not_above_divider` | Still "not above the divider voltage". The assertion that the worst case equals 3.214 V is dropped: the table-model diode already conducts at 5 V in. |
| `test_solver_rules.py::TestSingleSolver::test_only_one_solver_loop_in_the_app` | Also asserts that `circuit_model` and `bandwidth_model` can no longer be imported. |
| `test_solver_rules.py::TestSolverSettling::test_unsettled_flag_from_solver` | The case that fails to bracket was a negative ZZT; it is now an input that is not a number. |
| `test_solver_rules.py::TestSolverSettling::test_root_within_one_nanovolt` | 1 µV → 1 nV (owner decision, 2026-11-09). |
| `test_solver_rules.py::TestNoStaleOrFakeResults::test_unrelated_outputs_still_computed` | A blank ADC bits field now also blocks the analog error in LSB. |
| `test_solver_rules.py::TestAdcAndThresholds::test_threshold_factors_used` | The requirement text ("< VIL 0.83V") is built by the view now; the test asserts the limits of the two logic checks. |
| `test_solver_rules.py::TestPowerVerdict` (5 tests), `TestBlankRatingMargin::test_blank_rating_has_no_status` | Statuses are the words PASS / TIGHT / FAIL / "needs input" (they were `("✓ PASS", level)` pairs, or None for a blank rating). |
| `test_design_calculation.py::TestFullCalculation::test_operating_points_count` | "Five operating points" became the five level names. |
| `test_frequency.py::TestRcFilterBasics::test_total_capacitance`, `test_time_constant` | The fixture is the rail-Schottky design at 0 % tolerance (6428.57 Ω, 18 pF) instead of 100 Ω and 108 pF. |
| `test_frequency.py::TestEdgeCases::test_zero_resistance`, `test_invalid_thresholds_no_crash` | The unusable value is R1 = 0 (was a τ resistance of 0), and a VIH factor of 0.95 (was VIH 5 V). |
| `test_file_io.py::TestFileRoundTrip::test_save_and_reload` | The Zener fields became clamp-diode fields and a two-row reverse table. |
| `test_file_io.py::TestFileRoundTrip::test_json_format_version` | Version "2.0" (was "1.0"); the `clamp_diode`, `bandwidth` and `results` sections (was `zener`). |
| `test_app_state.py::TestNoHiddenDefaults::test_app_starts_blank`, `test_new_design_is_blank`, `test_saved_blank_is_null` | The Zener and preset assertions became clamp-diode fields and empty tables. |
| `test_app_state.py::TestBandwidthStartingValues` (3 kept tests) | The bandwidth fields are C_stray and the margin factor. |
| `test_app_state.py::TestUnreadableBlocksSave::test_out_of_range_does_not_block_save` | Extended: the saved file opens again and lists the value to fix. |
| `test_app_state.py::TestAtomicSave::test_failed_write_keeps_existing_file` | The simulated failure is patched into `div_format` (the writer moved there). |
| `test_app_state.py::TestLoading` (kept cases), `test_ui.py::test_malformed_file_keeps_current_design`, `test_failed_load_keeps_change_tracking` | The file under test is built from the baseline design or is an example file (was `results.div`). The UI test also checks that every problem is listed. |
| `test_ui.py::test_unit_combo_and_checkbox` | The checkbox is the clamp diode's "checked" box (was "Counter signed"). |
| `test_ui.py::test_new_design_clears_everything` | Rows whose optional input is blank show "--". Of the 0 V row only its input voltage is independent of the inputs now. The diode tables are checked to be empty (was: the preset selector is blank). |
