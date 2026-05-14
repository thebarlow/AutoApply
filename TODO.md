# Tasks for Matthew


## Improve Job Parse

Structure scraped job data into sections like : required qualifications/preferred qualifications before feeding it into the resume generator. The goal is that this will improve prompt output.

## Score function

- Line up the jobs required/preferred qualifications one to one with what the user profile has. 
- Shows what skills the user has, what skills they dont, what skills they have tangentially (think google cloud vs AWS)

## Refactor APIs
- separate resume md and resume pdf steps
- consider the actual user workflow when designing
- Import packages when used, not on start to speed up start time

## PDF config
- Take social links out of the template config, handle front matter separately.
- Improve UX for tex setup, or find alternative to tex templates

## Improve UX
- Welcome modal
- Help icons everywhere
- UI pills (?)

## Expand documentation
- consider audience (User vs employer)
- How to use
- Use visualization tools
- Docstrings for functions

