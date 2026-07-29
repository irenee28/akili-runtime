# Launch checklist

## Before making the repository public

- [ ] Run `python -m pip install -e ".[dev]"`.
- [ ] Run `python -m pytest`.
- [ ] Run `examples/quickstart.sh`.
- [ ] Replace any placeholder screenshots or links.
- [ ] Confirm no credentials, tokens, private repository paths or customer information exist.
- [ ] Review `docs/CLAIMS_AND_LIMITATIONS.md` line by line.
- [ ] Confirm V4 and E2.2 remain separate everywhere.
- [ ] Verify `SHA256SUMS`.
- [ ] Create the public GitHub repository as `akili-runtime`.
- [ ] Push with `publish_public_github.sh`.

## Before Hacker News

- [ ] A stranger can install and run the project.
- [ ] The README contains one clear example above the fold.
- [ ] At least one short demo video or GIF exists.
- [ ] Issues are enabled.
- [ ] You can stay available to answer technical questions.
- [ ] Write the submission and first comment in your own voice using `HN_LAUNCH_NOTES.md` only as factual notes.
