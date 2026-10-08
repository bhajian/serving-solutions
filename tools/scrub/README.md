# Site-identifier scrub

[Home](../../README.md) › [Tools](../README.md) › Scrub

A `git filter-repo --replace-text` map turns every site-specific identifier that
used to be committed into a `<PLACEHOLDER>`: the public LoadBalancer and SSH
addresses, node hostnames, node/pod/service IPs, PV names, the kube context, an
SSH user name and local home paths. The map lists the values being removed, so it
is **kept outside the repository** by the maintainer. The same map drives both steps:

1. **Working tree:** `python tools/scrub/apply.py PATH/TO/replacements.txt`
   rewrites tracked text files (binary files are skipped).
2. **History:** `git filter-repo --replace-text PATH/TO/replacements.txt --force`
   rewrites every commit, followed by a force-push of all branches and tags.

`tests/test_site_hygiene.py` fails if a public or private IPv4 address, a cloud
node hostname, a home-directory path or a literal kube context reappears.

Real values for a deployment go in a git-ignored `platform/site.env` and are
substituted by `tools/render_site.py`. A force-push does not remove GitHub's
cached pull-request refs (`refs/pull/*`); ask GitHub Support to purge them, and
treat the old LoadBalancer address as exposed (firewall or rotate it).
