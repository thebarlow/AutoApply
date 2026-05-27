# auto_apply

Semi-automated job scraping, tailored resume generation, and application management.

---


## Setup

```bash
git clone https://github.com/thebarlow/AutoApply.git
cd auto_apply
setup.bat
```

`setup.bat` installs Python if needed, creates the virtual environment, and deletes itself on success. You can also just run `start.bat` — it will detect and run `setup.bat` automatically on first launch.


---

## Starting the Server

```bash
# Windows
./start.bat
```

Navigate to [http://127.0.0.1:8080/](http://127.0.0.1:8080/)

---

## Onboarding process
New users are required to create a User Profile, which can seed data from their current master resume. 
User Profiles must contain an API key to an LLM. The onboarding process links to documents for users unfamiliar with the process.
This API key will determine what LLM models auto apply uses for all of its generation tasks.

---

## Further Help
More information about the application can be found by navigating the the server's help docs on [http://127.0.0.1:8080/docs](http://127.0.0.1:8080/docs) Once the server is running