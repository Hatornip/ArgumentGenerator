from flask import Flask, render_template, request, jsonify
from collections import defaultdict

app = Flask(__name__)

from collections import defaultdict

class ABAGenerator:
    def __init__(self):
        self.language = set()
        self.assumptions = set()
        self.contraries = {}
        self.rules = {}
        self.preferences = []

    def parse_input(self, input_text):
        lines = [line.strip() for line in input_text.split('\n') if line.strip()]
        for line in lines:
            if line.startswith('L:'):
                self.language = set(line[3:].strip(' []').split(','))
            elif line.startswith('A:'):
                self.assumptions = set(line[3:].strip(' []').split(','))
            elif line.startswith('C('):
                parts = line.split(':')
                ass = parts[0][2:-1].strip()
                contrary = parts[1].strip()
                self.contraries[ass] = contrary
            elif line.startswith('[') and ']:' in line:
                rule_id, rest = line.split(']:')
                rule_id = rule_id[1:]
                head, body = rest.split('<-')
                head = head.strip()
                body = [b.strip() for b in body.strip().split(',')] if body.strip() else []
                self.rules[rule_id] = (head, body)
            elif line.startswith('PREF:'):
                self.preferences = line[5:].strip().split('>')

    def get_arguments(self):
        arguments = []
        for ass in self.assumptions:
            arguments.append({
                'id': f'a{len(arguments)+1}',
                'claim': ass,
                'assumptions': {ass},
                'rules': set()
            })
        arg_dict = {arg['claim']: arg for arg in arguments}
        changed = True
        while changed:
            changed = False
            for rule_id, (head, body) in self.rules.items():
                body_args = []
                for b in body:
                    if b in arg_dict:
                        body_args.append(arg_dict[b])
                    else:
                        break
                else:
                    assumptions = set()
                    rules = set()
                    for ba in body_args:
                        assumptions.update(ba['assumptions'])
                        rules.update(ba['rules'])
                    rules.add(rule_id)
                    new_arg = {
                        'id': f'a{len(arguments)+1}',
                        'claim': head,
                        'assumptions': assumptions,
                        'rules': rules
                    }
                    if head not in arg_dict:
                        arg_dict[head] = new_arg
                        arguments.append(new_arg)
                        changed = True
        for arg in arguments:
            arg['assumptions'] = list(arg['assumptions'])
            arg['rules'] = list(arg['rules'])
        return arguments

    def get_attacks(self):
        attacks = []
        args = self.get_arguments()
        for a in args:
            for b in args:
                if a['claim'] in self.contraries.values() and any(ass in self.contraries and self.contraries[ass] == a['claim'] for ass in b['assumptions']):
                    attacks.append({
                        'attacker': a['id'],
                        'attacked': b['id']
                    })
        return attacks

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    input_text = request.json['input']
    generator = ABAGenerator()
    generator.parse_input(input_text)
    return jsonify({
        'language': list(generator.language),
        'assumptions': list(generator.assumptions),
        'contraries': generator.contraries,
        'rules': generator.rules,
        'preferences': generator.preferences,
        'arguments': generator.get_arguments(),
        'attacks': generator.get_attacks()
    })

if __name__ == '__main__':
    app.run(debug=True)

