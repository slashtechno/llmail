# LLMail  
Interact with Large Language Models (LLMs) via email.

### Features  
- Utilize any OpenAI-compatible API
    - At the time of writing, [OpenRouter](https://openrouter.ai/docs#models) offers free access to specific models with an OpenAI-compatible API
- Check every _n_ seconds 
- No need for a local database - uses IMAP

## Prerequisites  
### Python  
- Python ^3.11  
- Poetry (optional)  
- An API key from an OpenAI-compatible API  
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
1. Configure with the steps below  
2. `docker compose up -d`

### Configuration  
To configure the program, either use CLI flags (`--help` for more information) or environment variables.
It is recommended to just copy `.env.example` to `.env` and fill in the necessary information.

### How to uninstall  
- If you used Poetry, just delete the virtual environment and then the cloned repository