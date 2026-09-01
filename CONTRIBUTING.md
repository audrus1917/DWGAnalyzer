# Contributing

## Branch workflow

`dev` is the default integration branch. Create feature and fix branches from
`dev`, then open pull requests back into `dev`.

`main` contains release-ready code. Changes reach `main` through a release pull
request from `dev`; direct feature pull requests to `main` should be avoided.

Tagged commits on `main` use the `v*` format, for example `v0.1.0`. A tag starts
the release workflow, which runs the tests, builds the Python distribution, and
publishes the artifacts as a GitHub Release.

## Required checks

Pull requests to `dev` and `main` must pass the `CI / Tests` status check before
merge. Configure both branches to require pull requests, block force pushes and
deletions, and require this status check.
