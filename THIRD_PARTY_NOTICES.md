# Third-Party Notices

This file records third-party material retained in DebugOracle source
snapshots. It does not replace the license text or notices shipped with a
component. The original inventory and the release-0.3.0 closure receipt are
recorded in
[`docs/audits/public-alpha-p0-release-inventory.md`](docs/audits/public-alpha-p0-release-inventory.md)
and
[`docs/audits/public-release-0.3.0-provenance.md`](docs/audits/public-release-0.3.0-provenance.md).

## Main repository

### STM32L432 CMSIS-SVD

- **Location:** `examples/STM32L432.svd`
- **Component/version:** STMicroelectronics STM32L432 CMSIS-SVD, file version
  1.0
- **Copyright:** Copyright (c) 2024 STMicroelectronics
- **License:** Apache License 2.0, stated in the file header
- **Exact source:** modm's normalized STM32 CMSIS-SVD archive at commit
  `e79021accd49bf19bd0b16065f5471fb073ff3ac`, path
  `stm32l4/STM32L432.svd`
- **Integrity:** the pinned download and retained file both have SHA-256
  `d47c563ef28e9588a15ce4c158be8545929d702f0c9878e5410cff251e773edd`

The upstream archive records that its STM32 SVDs came from ST's site and were
normalized for line endings and trailing whitespace. The retained file header
is the license evidence.

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
  Existing per-file notices are retained. The exact official STM32CubeL4
  v1.18.2 package-license table is retained at
  `docs/audits/sources/STM32CubeL4-v1.18.2-LICENSE.md`; the pinned source commit,
  retrieval hash, generated-tree hash, and scope decision are recorded in the
  0.3.0 provenance receipt.

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

The recursive closure was verified for release 0.3.0. The provenance receipt
records every pinned nested gitlink and license-file hash. BTstack and the
CYW43 driver include non-commercial conditions; downstream users must review
those upstream terms for their intended use. DebugOracle does not relicense
submodule content.

## Excluded vendor material

STMicroelectronics and SEGGER manuals, generated document sidecars,
embeddings, and legacy extracted indexes are excluded from the public
snapshots. The complete pre-removal path and SHA-256 inventory is in the audit
artifact linked above. No rights in those excluded works are granted by the
DebugOracle project license.

## Python dependencies

The deterministic direct-dependency audit is retained at
[`docs/audits/public-alpha-p0-python-dependency-licenses.json`](docs/audits/public-alpha-p0-python-dependency-licenses.json).
It records the package configuration, authoritative package metadata, and
unresolved evidence separately; it is not a transitive software bill of
materials.

The supported base install pins **pypdf 6.16.1**, sourced from
<https://github.com/py-pdf/pypdf>, under the **BSD-3-Clause** license. Official
PyPI metadata for the 6.16.1 release declares `BSD-3-Clause`, records a
Trusted-Publishing provenance statement, and links the signed upstream tag.
This security release replaces the locally observed 6.9.2 baseline, which is
affected by published resource-consumption advisories in PDF parsing paths.

The base install also pins **packaging 26.0** for one canonical PEP 440
implementation shared by the installer. Official PyPI metadata declares
**Apache-2.0 OR BSD-2-Clause**, no runtime dependencies, and wheel SHA-256
`b36f1fef9334a5588b4166f8bcd26a14e521f2b55e6b9de3aaa80d3ff7a37529`.
Using the established PyPA implementation avoids divergent version ordering;
its exact pin keeps runtime resolution reproducible and adds one small,
dependency-free wheel.

The declared `docling`, `semantic`, and development extras remain visible in
package configuration so downstream experimentation does not require hidden
dependencies. Docling, semantic, and all are disabled for the 0.3.0 supported
installer: the local audit has no authoritative Docling or
sentence-transformers package metadata, no dependency lockfile exists, and no
Docling or embedding model/license selection is recorded. NumPy 1.26.4 was
locally observed under BSD-3-Clause, but that evidence does not close the
semantic profile. The `dev` extra is not an installer profile; its locally
observed direct packages are recorded in the audit and remain unpinned.
