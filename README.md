# LLMail  
Interact with Large Language Models (LLMs) via email.

### Features  
- Utilize any OpenAI-compatible API
- Check every _n_ seconds 
- No need for a local database - uses IMAP

## Prerequisites  
### Python  
- Python ^3.11
- Poetry (optional) 
- An API key from an OpenAI-compatible API
    - At the time of writing, [OpenRouter](https://openrouter.ai/docs#models) provides free access to select models
        - Right now, they are the only provider that will work due to the model being hard-coded (for now)

## Usage  
### Installation  
Cloning the repository is not required when installing from PyPi but is required when installing from source  
1. Clone this repo with `git clone https://github.com/slashtechno/llmail`  
2. `cd` into the cloned repository  
3. Install with [Poetry](https://python-poetry.org/) <!-- or [Docker](https://www.docker.com/) -->


#### Installing from PyPi with pip (recommended)  
This assumes you have the correct version of Python installed
1. `pip install llmail`  
    a. You may need to use `pip3` instead of `pip`  
2. `llmail`  

#### Poetry  
1. `poetry install`  
2. `poetry run -- llmail`  

<!-- #### Docker  -->
### Configuration  
To configure the program, either use CLI flags (`--help` for more information) or environment variables.  
It is recommended to just copy .env.example to .env and fill in the necessary information.

### How to uninstall  
- If you used Poetry, just delete the virtual environment and then the cloned repository