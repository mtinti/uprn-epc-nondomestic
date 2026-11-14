# Plan: publish to GitHub and publish the column provenance site

Status: done on 14 November 2026 ("What was done", at the end). It follows what
postcode-simd, datazone-ahah and uprn-epc did: a public repository under `mtinti`, tests on every
push, and a column provenance site on GitHub Pages served from a `gh-pages` branch.

## Words

- **Tracked file.** A file git would commit under the current `.gitignore`.
- **Provenance site.** The generated pages, one per column, source file, decision and check. It is
  built from committed metadata and holds no data value.
- **Pages.** GitHub Pages, the service that serves the site.

## What was checked before writing

- **Sign-in.** The GitHub CLI on this machine is signed in as `mtinti`, with the `repo` and
  `workflow` scopes. That is enough to create the repository, push the workflows and switch Pages
  on.
- **The name is free.** `mtinti/uprn-epc-nondomestic` does not exist. The README, `CITATION.cff`,
  `mkdocs.yml`, the Pages workflow and the site generator already use that name.
- **What would be tracked.** 87 files, 775 KB. The largest is `results/manifest.json` at 70 KB. The
  archive, the CSV, the note, the two data zone lists, the built CSV and the Parquet are ignored
  and stay local.
- **A checkout without data works.** In a copy holding only the tracked files, 101 tests pass and
  2 are skipped: the one that needs the built Parquet and the one that needs the pinned note.
- **The site builds.** In the same copy, the generator wrote 57 column pages, 5 source pages, 18
  decision pages and the check page, and `mkdocs build --strict` built 86 HTML pages without a
  warning.
- **How uprn-epc is served.** Its Pages source is the `gh-pages` branch at the root. The workflow
  pushes the built site to that branch and then asks Pages for a build. It was switched on by hand
  once.

Five things in the tracked files that a public reader would see. Each is a decision below.

- **Local paths in the review files.** The reviews of 14 November linked to files by their path on
  the author's machine. The links were dead for any other reader.
- **A server name, a database name and a connection string.** The notebook's step 1 carried the
  values of one site, inherited from uprn-epc and datazone-ahah, where they were public.
- **Local references in the ingestion plan.** It named two folders on the author's machine and a
  note that is not public.
- **A study name in a storage path.** `onedrive:dataset_healscot/...` is in the plan, the update
  guide and `SOURCES.md`. uprn-epc's public update guide has the same path.
- **The probes' container password.** `Epc_test_Pw0rd!` is in the two probe scripts, as in
  uprn-epc. It belongs to a container that the probe starts and that holds nothing. It is not a
  secret.

Not a concern: `TEST STREET` in four test files is synthetic. The build report prints one
certificate's register number, UPRN and dates, as uprn-epc's does, and no address or postcode.

## Decisions for you

| Decision | My suggestion | Why |
| --- | --- | --- |
| Repository name | `uprn-epc-nondomestic` | Named after the join key, like the three siblings, and already used in the files |
| Visibility | Public | The recipe is public by decision `recipe-public-data-private`. Nothing tracked holds a data value |
| Local paths in the reviews | Done 14 November 2026: the link targets only were rewritten, to paths inside the repository and to uprn-epc on GitHub | The text of each review stays as written. A reader can then follow the links |
| Server name, database name and connection string in the notebook | Decided 14 November 2026: removed. The committed notebook has an empty `CONN` and stops at step 1 until it is filled. A site copy is written from a file under `local/`, which git ignores | A load cannot start against a server by default, and no site's details are public |
| Local references in the ingestion plan | Name the public repository for uprn-epc. Describe the two local notes without a path | A reader cannot open them |
| The OneDrive path | Leave it | It is where the files are, and the sibling repository already shows it |
| First commit | One commit holding the whole tree, with the co-author line uprn-epc's commits carry | The work was not committed step by step. A made-up history would mislead |
| Version tag and Zenodo DOI | Decided 14 November 2026: release `v0.1.0` now | The Windows import route is untested. A fix after the load at HIC will be a second release |

## Step 1. Tidy the tree

1. Apply the decisions above on local paths, the server name and the plan's references.
2. Regenerate the notebook. Change the probe harness, which fills in step 1 by replacing the old
   placeholder text.
3. Put the provenance site and a test badge at the top of the README, as the siblings have them.
   The site link is added in step 3, when the page exists.
4. Run the tests and both container probes again. The notebook changed, so its probe is not
   optional.

**Done when**

- A search of the tracked files finds no path of the author's machine, no server name and no address.
- In a new virtual environment built from `requirements.txt`, as the test workflow builds it, a
  copy holding only the tracked files passes the tests with the same two skipped.
- `pip install -e ".[dev,docs]"`, as the Pages workflow installs it, then the site generator and
  `mkdocs build --strict`, succeed in that copy.

## Step 2. Create the repository and push

```bash
git init -b main
git add -A
git status --short | wc -l           # the tracked count of step 1, no more
git ls-files | grep -E '\.(7z|pdf|parquet|csv|gz|dbf)$'   # must print nothing
git commit -m "Non-domestic EPC ingestion: plan, build, SQL, loader, notebook, joins, provenance site"
```

The `gh-pages` branch and Pages come before the first push of `main`. The Pages workflow runs on
that push, and its last step asks Pages for a build. On a repository where Pages is off that
request fails, and the first run would be red for a reason that is not a defect.

```bash
gh repo create mtinti/uprn-epc-nondomestic --public \
  --description "Scottish non-domestic Energy Performance Certificates for SQL Server, one row per certificate, joinable by UPRN. Recipe public, data private."
git remote add origin https://github.com/mtinti/uprn-epc-nondomestic.git

# An empty gh-pages branch, so Pages has a branch to serve. It is made in a temporary folder,
# so the project folder, which holds the ignored data, is never switched to another branch.
tmp=$(mktemp -d) && git -C "$tmp" init -q -b gh-pages
touch "$tmp/.nojekyll" && git -C "$tmp" add .nojekyll && git -C "$tmp" commit -q -m "Start gh-pages"
git -C "$tmp" push https://github.com/mtinti/uprn-epc-nondomestic.git gh-pages

# Pages on, from gh-pages at the root, as for uprn-epc.
gh api -X POST repos/mtinti/uprn-epc-nondomestic/pages -f 'source[branch]=gh-pages' -f 'source[path]=/'

git push -u origin main
```

**Done when**

- The repository exists, public, with `main` and `gh-pages`.
- The `ci` workflow is green on the first push.

## Step 3. The provenance site

The Pages workflow does the rest on that same push: it runs the provenance tests, generates the
pages, builds the site, pushes it to `gh-pages` and waits for Pages to build it.

1. Watch the `pages` run to the end.
2. Open the site and three pages: the home page, `columns/IMPROVEMENT_RECOMMENDATIONS/` and
   `decisions/`.
3. Check on the live site what the tests check on the generated pages: every column has a page,
   no page holds a postcode shape or an address, and the home page names this project.
4. Add the site link and the badge to the README, set the repository's website to the site and
   its topics (`epc`, `energy-performance-certificate`, `uprn`, `scotland`, `sql-server`,
   `data-linkage`), and push. That second push also shows that an update reaches the site.
5. Add the repository to the Zenodo draft of the source archive as a related identifier. The draft
   stays unpublished.

**Done when**

- https://mtinti.github.io/uprn-epc-nondomestic/ serves the home page and the 57 column pages.
- A second push changed the README and the `pages` run was green again.
- A push to another branch publishes a preview under `preview/`, and deleting the branch removes
  it. This is tested once with a throwaway branch.

## What can go wrong, and what then

- **The Pages request is refused.** If the API call that switches Pages on fails, switch it on in
  the repository's settings (Pages, deploy from a branch, `gh-pages`, root) and run the `pages`
  workflow again. A second run with nothing to push still asks for a build and waits for it.
- **The first `pages` run is red although Pages is on.** The script can meet a build that the
  next one cancels. It already reads the recent builds and not only the latest. A rerun settles
  it.
- **Something private was pushed.** The repository is new and has no forks. Delete it, fix the
  tree and create it again. That is cleaner than rewriting history.

## What this plan does not do

- No release, no tag and no Zenodo DOI for the code, until you decide.
- No change to uprn-epc. Its postcode query still filters before it ranks, and its notebook has
  the same server name.
- No built data leaves the machine. The archive, the CSV and the Parquet are ignored by
  `.gitignore`, and step 2 checks the tracked list before the commit.

## After this

- Tag `v0.1.0` and make the GitHub release once the load at HIC has passed. Switch the repository
  on in Zenodo's GitHub settings before the release, in a browser, so the release gets a DOI. Add
  a `.zenodo.json` like datazone-ahah's first.
- Link the two EPC projects to each other in their READMEs.

## What was done, 14 November 2026

- **Repository.** https://github.com/mtinti/uprn-epc-nondomestic, public, one first commit of 88
  files. No archive, CSV, Parquet, note or data zone list is among them. A scan of every object of
  a fresh public clone found no site's server name, database name or connection options.
- **Tests.** The `ci` workflow passed on the first push. Before the push, the tests and the site
  build were run in a new environment on a copy holding only the tracked files.
- **Site.** https://mtinti.github.io/uprn-epc-nondomestic/ serves the home page, 57 column pages,
  the decisions and the checks. No page holds a postcode shape.
- **Previews.** A throwaway branch published a preview under `preview/`, and deleting the branch
  removed it.
- **Pages was switched on by the push of `gh-pages`**, not by the API call this plan gave. GitHub
  enables Pages by itself for a branch of that name. It also made `gh-pages` the default branch,
  because it was pushed first. The default was set back to `main`.
- **The Pages workflow runs on branches only.** As inherited it also ran on a tag push and
  published a preview for the tag that nothing removes. datazone-ahah has one such folder.
- **Release.** Version 0.1.0 was tagged and released the same day, and its code archived on
  Zenodo: 10.5281/zenodo.24226996 for every release, 10.5281/zenodo.24226997 for 0.1.0. Zenodo is not linked
  to the repository, so the archive was made by uploading the release's zip to a new record. The
  next release needs the same step, or the link switched on in Zenodo first.
