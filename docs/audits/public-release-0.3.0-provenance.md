# Public Release 0.3.0 Provenance Closure

**Recorded:** 2026-08-24
**Scope:** retained third-party inputs in the main repository and recursive
reference-workspace checkout

This receipt supplements the immutable pre-sanitization inventory. A hash
records byte identity; it does not replace the corresponding license or grant
additional rights.

## STM32CubeL4 generated firmware

- Generator evidence: every retained `stm32_1.ioc` records STM32CubeMX 6.17.0,
  database DB.6.0.170, `STM32Cube FW_L4 V1.18.2`, and STM32L432K(B-C)Ux.
- Package source: STMicroelectronics `STM32CubeL4` tag `v1.18.2`, peeled Git
  commit `703570fd63f1e8623e89df99285ead68f1665f83`.
- Package license source:
  `https://raw.githubusercontent.com/STMicroelectronics/STM32CubeL4/703570fd63f1e8623e89df99285ead68f1665f83/LICENSE.md`.
- Retrieved upstream bytes SHA-256:
  `f2e9ae84708af37b4a30f672e8d14f60800fbf5b6cb7a5af86431b461757c894`.
- Retained package-license copy:
  `docs/audits/sources/STM32CubeL4-v1.18.2-LICENSE.md`, SHA-256
  `b146929899f2078d0ff3a1f7dc50fbbe7baeb367d561ca5101009d0413833fee`.
  The retained text differs only by adding a final newline; the license table
  content is unchanged.
- Retained generated-tree relative-path/file-hash manifest SHA-256:
  `b773bb560f9bd084f47f3fba7e06f10a3b132dcdbc8d15aa0d5cdfc66ece789d`.
- License coverage relevant to retained files: CMSIS and CMSIS Device are
  Apache-2.0; STM32L4 HAL is BSD-3-Clause; STM32 Projects are ST SLA0044 with
  BSD-3-Clause for basic examples. Component license files and source notices
  remain present in each generated tree.

The generated application bytes are outputs of the recorded CubeMX setup, not
an assertion that a complete generated tree is byte-identical to an upstream
example. The generator configuration, package commit, retained license, local
component notices, and deterministic tree hash together form the acquisition
and integrity receipt.

## STM32L432 CMSIS-SVD

- Retained path: `examples/STM32L432.svd`.
- Exact pinned source:
  `https://raw.githubusercontent.com/modm-io/cmsis-svd-stm32/e79021accd49bf19bd0b16065f5471fb073ff3ac/stm32l4/STM32L432.svd`.
- Pinned source commit: `e79021accd49bf19bd0b16065f5471fb073ff3ac`.
- Retained and downloaded-source SHA-256:
  `d47c563ef28e9588a15ce4c158be8545929d702f0c9878e5410cff251e773edd`.
- License evidence: the retained file header states STMicroelectronics
  copyright and Apache-2.0. The source repository records that its STM32 SVDs
  originate from ST and are normalized for line endings/trailing whitespace.

The exact byte-for-byte pinned download was compared with the retained file on
2026-08-24.

## Reference workspaces and recursive Pico SDK closure

- Reference-workspaces gitlink:
  `36934bd168aef6541a3c74bf6ef579b15447505c`.
- Pico SDK gitlink: `a1438dff1d38bd9c65dbd693f0e5db4b9ae91779`
  (upstream release descriptor `2.2.0`).

| Component | Pinned commit | Retained license evidence | License-file SHA-256 |
|---|---|---|---|
| Pico SDK | `a1438dff1d38bd9c65dbd693f0e5db4b9ae91779` | `third_party/pico-sdk/LICENSE.TXT` (BSD-3-Clause) | `483f865953435b66c443dee7558debe3cc3cf8fcbb6a112fd9fc6a795d53f1f6` |
| BTstack | `501e6d2b86e6c92bfb9c390bcf55709938e25ac1` | `lib/btstack/LICENSE` (upstream terms include a non-commercial condition) | `10aa5f952979a9fa2f58bf63c1390c9795b41f8eca405ab975ab926e4d14fc5a` |
| CYW43 driver | `dd7568229f3bf7a37737b9e1ef250c26efe75b23` | `lib/cyw43-driver/LICENSE` (upstream terms include a non-commercial condition) | `0ce42360898b7c3f168317b559d4783b55c892751580c2a12c76b548aa5858fb` |
| lwIP | `77dcd25a72509eb83f72b033d219b1d40cd8eb95` | `lib/lwip/COPYING` (BSD-style) | `ef4aac92e05e87cd1cdc140870ed52206ba03d4a7fe46c1e11d7ffa6c87d252b` |
| Mbed TLS | `107ea89daaefb9867ea9121002fbbdf926780e98` | `lib/mbedtls/LICENSE` (Apache-2.0 OR GPL-2.0-or-later) | `9b405ef4c89342f5eae1dd828882f931747f71001cfba7d114801039b52ad09b` |
| Mbed TLS framework | `94599c0e3b5036e086446a51a3f79640f70f22f6` | `lib/mbedtls/framework/LICENSE` (Apache-2.0 OR GPL-2.0-or-later) | `11402351e38392230bb8934ba1095c0c0049a296c0f8821f76e4672dff54b490` |
| TinyUSB | `86ad6e56c1700e85f1c5678607a762cfe3aa2f47` | `lib/tinyusb/LICENSE` (MIT) | `b171720e8a442e7a3957d83c62cd3299dbb29da3db534cc626f9dded0de2ca44` |

These dependencies remain Git submodules owned and licensed by their upstream
projects. The DebugOracle Apache-2.0 license does not relicense them. A
recursive checkout at the recorded gitlinks was used to verify the closure and
license-file hashes. In particular, downstream users must review the BTstack
and CYW43 non-commercial conditions for their intended use.

## Closure decision

The four historical public-export evidence gaps are closed by this receipt:
the exact STM32 package license is retained, the generated-tree acquisition
configuration and integrity hash are recorded, the SVD has an exact pinned
byte-identical source, and the recursive Pico SDK gitlink/license closure is
enumerated. Optional Python profiles remain deliberately disabled and are not
part of this provenance decision.

On 2026-08-24, the repository maintainer confirmed that DebugOracle remains
licensed under Apache-2.0, including its permission for commercial use. The
BTstack and CYW43 sources are optional nested upstream submodules used only by
the reference-workspace development closure; they are not Python runtime
dependencies and are not included in the DebugOracle wheel. Their upstream
terms therefore remain separate and do not change the DebugOracle project
license. Normal wheel installation does not require a recursive submodule
checkout.
