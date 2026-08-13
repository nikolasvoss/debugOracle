# Third-Party Notices

This file records third-party material retained in the planned DebugOracle
public-alpha source snapshots. It does not replace the license text or notices
shipped with a component. The evidence and release-blocking gaps behind this
summary are recorded in
[`docs/audits/public-alpha-p0-release-inventory.md`](docs/audits/public-alpha-p0-release-inventory.md).

## Main repository

### STM32L432 CMSIS-SVD

- **Location:** `examples/STM32L432.svd`
- **Component/version:** STMicroelectronics STM32L432 CMSIS-SVD, file version
  1.0
- **Copyright:** Copyright (c) 2024 STMicroelectronics
- **License:** Apache License 2.0, stated in the file header
- **Source:** STMicroelectronics STM32 CMSIS-SVD data. The snapshot does not
  retain the exact upstream URL, tag, or download receipt; this is a
  release-blocking provenance gap.

`tests/fixtures/sample.svd` is a small project-authored synthetic fixture, not
the ST SVD.

## Reference-workspaces repository

The paths below are relative to `examples/debugoracle-reference-workspaces/`.

### STM32CubeL4 generated firmware

The following five generated trees are retained:

- `stm32/fault/generated/`
- `stm32/hardfault/generated/`
- `stm32/healthy/generated/`
- `stm32/peripheral-miscfg/generated/`
- `stm32/watchdog-timeout/generated/`

Each tree's checked-in `stm32_1.ioc` records STM32CubeMX 6.17.0,
STM32Cube database DB.6.0.170, and `STM32Cube FW_L4 V1.18.2` for device
STM32L432K(B-C)Ux. The official package source is
<https://github.com/STMicroelectronics/STM32CubeL4/tree/v1.18.2> (also
distributed from <https://www.st.com/en/embedded-software/stm32cubel4.html>).

Retained third-party components inside every tree are:

- **CMSIS Core(M) 5.3.0**, Arm Limited (with one IAR Systems compiler header),
  Apache-2.0. The full license is retained at `Drivers/CMSIS/LICENSE.txt` and
  SPDX/license notices remain in the source files.
- **STM32L4 CMSIS Device 1.7.5**, STMicroelectronics, Apache-2.0 fallback terms
  stated by `Drivers/CMSIS/Device/ST/STM32L4xx/LICENSE.txt`; a full Apache-2.0
  copy is retained as `License.md` in the same directory.
- **STM32L4 HAL/LL Driver 1.13.6**, STMicroelectronics, BSD-3-Clause fallback
  terms stated by `Drivers/STM32L4xx_HAL_Driver/LICENSE.txt`; copyright and
  component-license notices remain in the source files.
- **STM32CubeMX-generated Core/startup/linker content**, STMicroelectronics.
  Existing per-file notices are retained, but the package-level
  `Package_license` referenced by component notices is absent. This content is
  blocked from public release until the exact STM32CubeL4 1.18.2 package
  license is added and reviewed.

The five generated trees were byte-identical at the audited baseline. Their
deterministic relative-path/file-hash manifest SHA-256 was
`b773bb560f9bd084f47f3fba7e06f10a3b132dcdbc8d15aa0d5cdfc66ece789d`.

### Raspberry Pi Pico SDK

- **Location:** `third_party/pico-sdk` Git submodule
- **Pinned commit:** `a1438dff1d38bd9c65dbd693f0e5db4b9ae91779`
- **Source:** <https://github.com/raspberrypi/pico-sdk/tree/a1438dff1d38bd9c65dbd693f0e5db4b9ae91779>
- **License:** BSD-3-Clause at the upstream repository root; component-level
  exceptions/notices remain governed by the recursively checked-out upstream
  tree.

The baseline checkout did not initialize this submodule, so its license and
recursive submodule closure must be verified in the clean-clone release gate.

## Excluded vendor material

STMicroelectronics and SEGGER manuals, generated document sidecars,
embeddings, and legacy extracted indexes are excluded from the public
snapshots. The complete pre-removal path and SHA-256 inventory is in the audit
artifact linked above. No rights in those excluded works are granted by the
DebugOracle project license.

## Python dependencies

Python package and optional-profile licensing is intentionally not asserted
here yet. Public-alpha plan step 5 requires a separately generated dependency
license inventory; unresolved optional dependencies must remain disabled.
