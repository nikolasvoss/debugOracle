# Public Alpha P0 Pre-Sanitization Inventory

**Audit state:** complete for the recorded Git commit baselines; unresolved
items below block public export.

## Scope and method

This audit was captured before reference sanitization. It covers tracked files
in:

- main repository commit `b9d103e840907b6b5a125cb48f4e06a6ef6b4d9e`
- reference-workspaces commit `23c3f1317d78712016cbcd32624551de7f58b3e1`

Files were enumerated from each repository's Git index. SHA-256 identifies
byte-identical copies; it is evidence of content identity, not a license or an
origin claim. Main-repository paths are prefixed `main:` and reference paths
are prefixed `ref:` below.

## Verified retained inventory

| Component | Retained locations | Version/provenance evidence | License evidence | State |
|---|---|---|---|---|
| STM32L432 CMSIS-SVD | `main:examples/STM32L432.svd` | File `<version>1.0</version>` and ST copyright header; SHA-256 `d47c563ef28e9588a15ce4c158be8545929d702f0c9878e5410cff251e773edd` | File header says Apache-2.0 | Blocked: exact upstream URL/tag or download receipt is absent |
| CMSIS Core(M) | `ref:stm32/{fault,hardfault,healthy,peripheral-miscfg,watchdog-timeout}/generated/Drivers/CMSIS/` | `cmsis_version.h` defines 5.3.0; per-file versions/notices retained | Apache-2.0 text at `Drivers/CMSIS/LICENSE.txt`; SPDX headers name Arm and IAR where applicable | Verified component/version/license |
| STM32L4 CMSIS Device | Same five trees under `Drivers/CMSIS/Device/ST/STM32L4xx/` | `stm32l4xx.h` defines 1.7.5 | Component `LICENSE.txt` states Apache-2.0 fallback; full `License.md` retained | Blocked pending package license noted below |
| STM32L4 HAL/LL | Same five trees under `Drivers/STM32L4xx_HAL_Driver/` | `stm32l4xx_hal.c` defines 1.13.6 | Component `LICENSE.txt` states BSD-3-Clause fallback; source notices retained | Blocked pending package license noted below |
| STM32CubeMX generated Core/startup/linker material | Same five `generated/` trees and corresponding copied ST files under each `app/` tree | Every `.ioc` records CubeMX 6.17.0, DB.6.0.170, `STM32Cube FW_L4 V1.18.2`, STM32L432K(B-C)Ux | Per-file notices retained; package license absent | **Release blocker** |
| Raspberry Pi Pico SDK | `ref:third_party/pico-sdk` | Gitlink `a1438dff1d38bd9c65dbd693f0e5db4b9ae91779`; public upstream URL in `.gitmodules` | Upstream root declares BSD-3-Clause | Blocked until recursive clean clone verifies license/notice closure |

All five `.ioc` files were byte-identical at capture time (SHA-256
`f6631ba1963e419e2360b6358d16acfdc52e158964ccd6dc1d213e499c0f772b`).
Each generated tree contained 96 tracked files, and all five complete trees had
the same deterministic relative-path/file-hash manifest SHA-256:
`b773bb560f9bd084f47f3fba7e06f10a3b132dcdbc8d15aa0d5cdfc66ece789d`.

The official package references used for review are the ST-maintained
[`STM32CubeL4` v1.18.2 tag](https://github.com/STMicroelectronics/STM32CubeL4/tree/v1.18.2)
and [STM32CubeL4 product page](https://www.st.com/en/embedded-software/stm32cubel4.html).
They corroborate that the named package contains CMSIS and HAL/LL; they do not
prove that the checked-in bytes were obtained from either location.

## Excluded vendor assets and derived data

Every path in this section is excluded from the public snapshot. There were
seven tracked vendor PDF copies (three unique byte streams), five tracked
`*.dbgoracle-docs/` directories containing 13 files, and four legacy extracted
directories containing 12 files. Because one `*.dbgoracle-docs/` directory is
derived from project-authored `RM0394_excerpt.md`, there are 25 unique derived
paths after overlap/deduplication, of which 22 are in the reference repository
and three are in main.

### Vendor PDF hash groups

| SHA-256 | Paths |
|---|---|
| `04d561072f4779a0bed4ae220ad30c59473e02dd9279c7e46da49177221b5b6e` | `main:examples/stm32l423_reference_manual.pdf`; `ref:stm32/{hardfault,peripheral-miscfg}/doc/stm32l423_reference_manual.pdf` |
| `9f556e146bcf199bcf70cc0adeec69f6b77d7ef817bef95f0da8aaef759e0f6a` | `ref:stm32/{fault,healthy}/doc/UM08001_JLink.pdf` |
| `c99fa9f5d79df1bd99a2806bcb5fc7dda7da59947b15464337fc6e0d27f8d799` | `ref:stm32/{fault,healthy}/doc/J-Link_Commander_SEGGER_Knowledge_Base.pdf` |

### Generated/derived hash groups

Brace notation denotes one path per named workspace. `main:examples/` contains
the main copy; all other paths in this table are under `ref:stm32/`.

| SHA-256 | Paths |
|---|---|
| `00b539429e929bfb59f44d45dbb90e3bdfb2f2695473850771cdabd3b50d9724` | `main:examples/stm32l423_reference_manual.pdf.dbgoracle-docs/embeddings.npy`; `{hardfault,peripheral-miscfg}/doc/stm32l423_reference_manual.pdf.dbgoracle-docs/embeddings.npy` |
| `582c6626cb08ae606461231c3a7ca387e484e5c0ded69ed9bf12004f372625f3` | `main:examples/stm32l423_reference_manual.pdf.dbgoracle-docs/index.json`; `{hardfault,peripheral-miscfg}/doc/stm32l423_reference_manual.pdf.dbgoracle-docs/index.json` |
| `e12950632b41b32cf6e248258748aaf5108e506e6df4342b2bf58bdbb9bbbaa5` | `main:examples/stm32l423_reference_manual.pdf.dbgoracle-docs/envelope.json`; `{hardfault,peripheral-miscfg}/doc/stm32l423_reference_manual.pdf.dbgoracle-docs/envelope.json` |
| `3b6d09d19561c3d98341d9775a85e10f6b55c229c7a271589ca1c621c2ae7612` | `{fault,healthy}/doc/J-Link_Commander_SEGGER_Knowledge_Base_llm/chunks.jsonl` |
| `05c88bc40c809ff198d37014017b8c2c9c60ab435da81d425cf62dc9be1f9b08` | `{fault,healthy}/doc/J-Link_Commander_SEGGER_Knowledge_Base_llm/document.md` |
| `6539be08eb0651b0a2f464d6f7018da2f4d6a96e42845564be0ecb8508ddfcc3` | `{fault,healthy}/doc/J-Link_Commander_SEGGER_Knowledge_Base_llm/report.json` |
| `493dd9cab7e13301713ca0eded6f33c90d33dd2ea961298f772f7346b3dd66d7` | `{fault,healthy}/doc/jlink_llm/chunks.jsonl` |
| `2f87ff8a8122b8fb85e188188749c1e4cf1c8bb7f85e843c5bef838bd5be7e39` | `{fault,healthy}/doc/jlink_llm/document.md` |
| `68e1b023f081bbee88b0b89de96b79e3cf13b9d65400997823113c0469400035` | `{fault,healthy}/doc/jlink_llm/report.json` |
| `a4fc557c78117866a3187d9433e86bb1cde5051f44134bfbd350fb94b1043183` | `healthy/doc/UM08001_JLink.pdf.dbgoracle-docs/envelope.json` |
| `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` | `healthy/doc/UM08001_JLink.pdf.dbgoracle-docs/index.json` |
| `322153f6670a93ef5dddb913dc589034b58a9bc1c8b4032c4d1c4c6c25e544cb` | `peripheral-miscfg/doc/RM0394_excerpt.md.dbgoracle-docs/envelope.json` |
| `11dfe4cfeac51705f5a293c1d118f9ede37b2642e2274f221c33b3e09b57d3fa` | `peripheral-miscfg/doc/RM0394_excerpt.md.dbgoracle-docs/index.json` |

## Retained license-root identity groups

The following hashes prove that each of the five generated trees carried the
same notice copies at capture time:

| SHA-256 | Relative path in each generated tree |
|---|---|
| `e03ba41d7fab20700769fe4118bab50d800cb74f990353a05d2f5fff1c228363` | `Drivers/CMSIS/LICENSE.txt` |
| `135fb2d86e9ecdf6824cc3bba21c72b8e380c07b055fbebb6b995463eb609baf` | `Drivers/CMSIS/Device/ST/STM32L4xx/LICENSE.txt` |
| `dadb755f51d36614173b28c5790cb4a991e8f4cc822e5b634fd66a4f4145824d` | `Drivers/CMSIS/Device/ST/STM32L4xx/License.md` |
| `d5a162f3eaf2b7b6762f00700017cae5695ebbdce7932fead8316448baafd9c1` | `Drivers/STM32L4xx_HAL_Driver/LICENSE.txt` |

## Release-blocking gaps

1. **STM32 package license absent.** The retained ST component notices refer to
   a package-level `Package_license`, but no such file exists in the audited
   snapshot. Obtain it from the exact STM32Cube FW_L4 V1.18.2 distribution,
   preserve it with each retained generated component root, and review its
   terms before export.
2. **Generated-tree acquisition receipt absent.** The `.ioc` files prove the
   generator/package selection, not the origin of the checked-in bytes. Record
   the exact archive/tag, upstream commit where applicable, retrieval method,
   and archive hash when the package license is supplied.
3. **STM32L432 SVD origin incomplete.** Its header verifies owner and license,
   but the exact upstream release/source and acquisition hash are unknown.
4. **Pico SDK checkout not initialized at baseline.** The Gitlink and public
   URL are known, but its license file and recursive submodule set were not
   locally present. The public clean-clone gate must verify them at the pinned
   commit.
5. **Optional Python profiles fail closed.** The completed dependency audit is
   recorded in `public-alpha-p0-python-dependency-licenses.json`; `docling`,
   `semantic`, and composed `all` remain disabled until their package and model
   licensing is resolved.

No blocked item may be converted to "verified" without adding traceable source
evidence. Missing evidence is not permission to infer provenance or licensing.
