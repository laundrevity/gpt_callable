import subprocess
import openai
import inspect
import pathlib
import json
import re
import os
openai.api_key = os.getenv('OPENAI_API_KEY')

def gpt_callable(func):
    func.is_gpt_callable = True
    return func

def parse_description(func):
    param_description = {}
    doc = inspect.getdoc(func) or ""
    params = re.findall(r":param (.*?): ([\S\s]*)(?=:param|\Z)", doc)  # Modified regex
    
    for param, description in params:
        description = re.sub("\n\s+", " ", description)
        param_description[param] = description.strip()

    return param_description

class Agent:
    def __init__(self):
        self.FUNCTIONS = []
        for func_name, func in inspect.getmembers(self, inspect.ismethod):
            if getattr(func, "is_gpt_callable", False):
                doc = inspect.getdoc(func) or ""
                func_description = re.search(r"^([\s\S]*?)(?=^:param|\Z)", doc, re.MULTILINE).group(1).strip()
                param_description = parse_description(func)
                sig = inspect.signature(func)
                func_info = {
                    'name': func_name,
                    'description': func_description,
                    'parameters': {
                        'type': 'object',
                        'properties': {
                            name: {
                                'type': 'string',
                                'description': param_description.get(name, "No description provided.")
                            }
                            for name in sig.parameters
                        }
                    }
                }
                # Check for required params
                required = [name for name, param in sig.parameters.items()
                            if param.default == inspect.Parameter.empty and
                            param.kind in [
                                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                                inspect.Parameter.POSITIONAL_ONLY
                            ]]
                if required:
                    if func_info.get('required'):
                        func_info['required'] += required
                    else:
                        func_info['required'] = required
                self.FUNCTIONS.append(func_info)
    
    @gpt_callable
    def execute_linux_commands(self, commands_json: str):
        """
        Execute list of Linux commands and return stdout for each.
        :param commands_json: Stringified JSON of list of commands to execute. Each element
                              of the list needs a string attribute `command` and optional 
                              attribute `args` which is a list of arguments.
                              Redirection should be an argument by itself.
        """
        commands = json.loads(commands_json)
        result_str = ''
        for command_json in commands:
            command = command_json['command']
            args = command_json.get('args', [])
            redirect_out = None
            
            if '>' in args:  # detect redirection
                redirect_index = args.index('>')
                redirect_out = args[redirect_index + 1]  # get output file 
                args = args[:redirect_index]  # remove '> and the filename' symbols 

            try:
                if redirect_out:
                    with open(redirect_out, 'w') as fp:
                        result = subprocess.run([command] + args, stdout=fp)
                    msg = f'REDIRECTED_TO_FILE: {redirect_out}\n' 
                else:
                    result = subprocess.check_output([command] + args, shell=False)
                    msg = result.decode('utf-8')
            except subprocess.CalledProcessError as e:
                msg = f"Error executing command: {e.output.decode('utf-8')}"
                print(msg)
            except FileNotFoundError:
                msg = f"Command not found: {command}"
                print(msg)
            except Exception as e:
                msg = f"An unexpected error occurred: {e}"
                print(msg)

            result_str += msg + '\n'

        return result_str.strip()
    
    @gpt_callable
    def write_state_file(self):
        """
        Writes a state file state.txt with the content of all relevant files in the current directory
        and subdirectories (excluding venv).
        """
        types = ['.yml', '.txt', '.py', 'Dockerfile']
        files = [f for f in pathlib.Path().rglob("*") if f.is_file()]
        files = [f for f in files if f.suffix in types or f.name in types]
        state_file_path = pathlib.Path('state.txt')
        if state_file_path.exists():
            state_file_path.unlink()
        with state_file_path.open('w') as state_file:
            for file in files:
                if 'venv' not in str(file):
                    state_file.write(f'---{str(file)}---\n')
                    with file.open() as f:
                        for i, line in enumerate(f, start=1): # start enumeration from 1
                            state_file.write(f'{i}:: {line}') # write line number and content
                    state_file.write('\n\n')
            
        return 'State file has been written'


    async def get_gpt_response(self, prompt: str):
        response = await openai.ChatCompletion.acreate(
            model='gpt-4',
            messages=[{'role': 'user', 'content': prompt}],
            functions=self.FUNCTIONS
        )
        return response['choices'][0]['message']
