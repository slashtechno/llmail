# LLMail  
Interact with Large Language Models (LLMs) via email.
[![Watch the video](https://img.youtube.com/vi/0YHQaxvxGoI/maxresdefault.jpg)](https://youtu.be/0YHQaxvxGoI)


### Features  
- Utilize any OpenAI-compatible API with any available model
    - At the time of writing, [OpenRouter](https://openrouter.ai/docs#models) offers free access to specific models with an OpenAI-compatible API
    - [Ollama](https://github.com/ollama/ollama) has an OpenAI-compatible API and allows for easy local deployment of LLMs  
- Customize the behavior of the LLM with a system prompt
- Easily run in a Docker container
    - The default `docker-compose.yml` file uses `restart: unless-stopped` to ensure the container restarts after a reboot or if it crashes  
- Check every _n_ seconds 
- No need for a local database - uses IMAP

## Prerequisites  
### General
- Access to an OpenAI-compatible API (including locally hosted LLMs)  
- An email account that supports IMAP and SMTP  
### Python  
- Python ^3.11  
- Poetry (optional)  
### Docker
- Docker  

## Usage  
### Installing from PyPi with `pip` (recommended)  
This assumes you have the correct version of Python installed
1. `pip install llmail`  
    a. You may need to use `pip3` instead of `pip`  
2. `llmail`  

### Installation from source or with Docker
Cloning the repository is not required when installing from PyPi but is required when installing from source  
1. Clone this repo with `git clone https://github.com/slashtechno/llmail`  
2. `cd` into the cloned repository  
3. Install and run with one of the following methods:



#### Poetry
1. `poetry install`  
2. `poetry run -- llmail`  

#### Docker
1. Configure a `.env` file (see Configuration below)  
    a. You can also edit the `docker-compose.yml` file directly but by default it loads the `.env` file
2. `docker compose up -d`

### Configuration  
To configure the program, either use CLI flags (`--help` for more information) or environment variables (view `.env.example` for more information).
It is recommended to just copy `.env.example` to `.env` and fill in the necessary information.
### Interacting with the LLM  
Once the program is running, you can send an email to the address you configured with whatever the subject is set to. The body of the email will be sent to the LLM, and the response will be sent back to you.  
For example, if in `.env` you set `SUBJECT_KEY=llmail`, you would send an email with the subject `llmail` to the configured email address.  
### How to uninstall  
- If you used `pip`, run `pip uninstall llmail`
- If you used Poetry, just delete the virtual environment and then the cloned repository  
- If you used Docker, run `docker compose down` in the cloned repository and then delete the cloned repository  