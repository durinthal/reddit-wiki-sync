# Reddit Wiki Sync

Save wiki pages of subreddits to a git repository! There's a rudimentary revision system on reddit, but it can only show the full page at any given revision or a diff between two revisions.

This allows for use of tools like [git blame](https://www.git-scm.com/docs/git-blame) to figure out exactly when specific lines were changed without needing to crawl through a page's history and check multiple revisions.

## Getting Started

1. [Create a new repository from this template.](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-repository-from-a-template)

2. Enable [write permissions for `GITHUB_TOKEN`](https://docs.github.com/en/actions/security-guides/automatic-token-authentication#modifying-the-permissions-for-the-github_token) in the repository.

3. Set [configuration variables](https://docs.github.com/en/actions/learn-github-actions/variables#creating-configuration-variables-for-a-repository) and [secrets](https://docs.github.com/en/codespaces/managing-codespaces-for-your-organization/managing-encrypted-secrets-for-your-repository-and-organization-for-github-codespaces#adding-secrets-for-a-repository) for the repository following the below names.

4. Enable the [scheduled workflow](https://docs.github.com/en/actions/managing-workflow-runs/disabling-and-enabling-a-workflow) if you want to have automatic updates and change the [scheduled time](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#schedule) if appropriate (default: [6:25 UTC every day](https://crontab.guru/#25_6_*_*_*)).


## Caveats and Reminders

* If including mod-only pages you probably want to make sure your [repository is private](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility) as well.
* The initial sync may take several hours if the subreddit has a long history of revisions to wiki pages, so you might want to check out the repository to run it manually [and not under Github Actions](https://docs.github.com/en/actions/learn-github-actions/usage-limits-billing-and-administration#usage-limits).
* Specific pages can have _many_ revisions and you may want to ignore them, such as `usernotes` if the subreddit uses [Toolbox's user notes](https://www.reddit.com/r/toolbox/wiki/docs/usernotes).
* Delisted pages will remain even if the unlisted pages flag isn't set, they must be manually pruned.
* As currently set up, this only works for one subreddit per repository. Modifying the workflows to take a subreddit as an input or use [environments](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment) would be ways of handling multiple subreddits.

## Environment Variables

* SUBREDDIT_NAME_TO_ACT_ON: The name of the subreddit that has the wiki you wish to archive without the leading `/r/`, e.g. `anime`.
* REDDIT_USERNAME: Name for authenticating reddit user.
* REDDIT_CLIENT_ID: [OAuth Client ID](https://github.com/reddit-archive/reddit/wiki/OAuth2) for authenticating app.
* REDDIT_USER_AGENT: [User Agent string](https://github.com/reddit-archive/reddit/wiki/API) for authenticating app.

For customizing the scheduled workflow also include these:

* SCHEDULED_SYNC_PAGES: Comma-separated list of wiki page names to save, or all if `*`. (default `*`)
* SCHEDULED_SYNC_IGNORE: Comma-separated list of wiki page names to ignore. (default: none)
* SCHEDULED_SYNC_FULL: `true` to include all of a page's history rather than just recent updates. Ignores unlisted pages. (default: `false`)
* SCHEDULED_SYNC_MOD: `true` to save mod-only pages as well, or just publicly visible pages if false. (default: `false`)
* SCHEDULED_SYNC_UNLISTED: `true` to save unlisted pages as well, if checking recent revisions. Not compatible with full list. (default: `false`)

## Environment Secrets

* REDDIT_CLIENT_SECRET: [OAuth Client Secret](https://github.com/reddit-archive/reddit/wiki/OAuth2) for authenticating app.
* REDDIT_USER_PASSWORD: Password for authenticating reddit user.
* REDDIT_TOTP_SECRET: ___(optional)___ Only add if the authenticating reddit user has two-factor authentication enabled. 