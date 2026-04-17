@echo off
git filter-branch -f --env-filter "if \"$GIT_AUTHOR_NAME\" == \"Antigravity AI\" set GIT_AUTHOR_NAME=M SRAVANTHI&& set GIT_AUTHOR_EMAIL=sravanthim674@gmail.com" -- --all
