# Release checklist

## Repository content

- [ ] `start-dev.bat test` passes
- [ ] `scripts/leak_scan.ps1` passes on `dist/github/k210-poker-vision`
- [ ] no dataset images or optimizer checkpoints are staged
- [ ] no MaixPy v4, Darknet source dump, car project or vendor driver is staged
- [ ] `NOTICE.md` retains CC BY 4.0 and algorithm attribution
- [ ] metrics correspond to the committed evaluation command
- [ ] README separates desktop, simulator, physical and unverified claims
- [ ] generated media has no audio, metadata or visible personal information

## Binary release

- [ ] default physical KModel is `060163...fc3b6a`
- [ ] e20 candidate is labelled `physical-verification-pending`
- [ ] ONNX, KModel SHA-256 and byte size recorded
- [ ] KModel input/output shape recorded
- [ ] model license and dataset attribution included
- [ ] release notes state whether physical K210 verification passed
- [ ] SD installer verifies FAT32, backups and copied hashes
- [ ] PC launcher uses shared environment first and local uv fallback second

## Publication

- [ ] run `scripts/leak_scan.ps1` against the generated public copy
- [ ] review the staged diff
- [ ] confirm repository visibility and target branch
- [ ] push the reviewed `main` branch
- [ ] create tag `v1.0.0` and upload the files listed in `SHA256SUMS.txt`
