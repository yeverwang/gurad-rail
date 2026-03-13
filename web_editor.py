"""
Web-based Contract Editor for Guardrail Engine

A Flask application for viewing, editing, and validating YAML contracts.
Provides a user-friendly interface for managing agent governance policies.

Usage:
    python web_editor.py

Then open http://localhost:5000 in your browser.
"""

from flask import Flask, render_template, request, jsonify, send_from_directory
import yaml
import os
from pathlib import Path
from typing import Dict, Any, List
from guardrail.contract_loader import ContractLoader
from guardrail.models import Contract

app = Flask(__name__)

# Configuration
CONTRACTS_DIR = Path("contracts")
CONTRACTS_DIR.mkdir(exist_ok=True)


def get_contract_files() -> List[Dict[str, Any]]:
    """获取所有合约文件的列表"""
    contracts = []
    for file_path in CONTRACTS_DIR.glob("*.yaml"):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                contracts.append({
                    'filename': file_path.name,
                    'contract_id': data.get('metadata', {}).get('contract_id', 'Unknown'),
                    'version': data.get('metadata', {}).get('version', 'Unknown'),
                    'status': data.get('metadata', {}).get('status', 'Unknown'),
                    'path': str(file_path)
                })
        except Exception as e:
            contracts.append({
                'filename': file_path.name,
                'contract_id': 'Error',
                'version': '',
                'status': 'Error',
                'path': str(file_path),
                'error': str(e)
            })
    return sorted(contracts, key=lambda x: x['filename'])


def validate_contract_yaml(yaml_content: str) -> Dict[str, Any]:
    """验证合约 YAML 内容"""
    try:
        # Parse YAML
        data = yaml.safe_load(yaml_content)

        # Validate with Pydantic
        contract = Contract.model_validate(data)

        return {
            'valid': True,
            'message': 'Contract is valid',
            'contract_id': contract.metadata.contract_id,
            'version': contract.metadata.version,
            'status': contract.metadata.status
        }
    except yaml.YAMLError as e:
        return {
            'valid': False,
            'error': 'YAML Syntax Error',
            'message': str(e)
        }
    except Exception as e:
        return {
            'valid': False,
            'error': 'Validation Error',
            'message': str(e)
        }


@app.route('/')
def index():
    """主页：显示所有合约列表"""
    contracts = get_contract_files()
    return render_template('index.html', contracts=contracts)


@app.route('/api/contracts')
def list_contracts():
    """API: 获取所有合约列表"""
    return jsonify(get_contract_files())


@app.route('/api/contract/<filename>')
def get_contract(filename):
    """API: 获取指定合约内容"""
    file_path = CONTRACTS_DIR / filename

    if not file_path.exists():
        return jsonify({'error': 'Contract not found'}), 404

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 也返回解析后的数据用于显示
        data = yaml.safe_load(content)

        return jsonify({
            'filename': filename,
            'content': content,
            'data': data
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/contract/<filename>', methods=['POST'])
def save_contract(filename):
    """API: 保存合约内容"""
    try:
        content = request.json.get('content', '')

        # 验证 YAML
        validation = validate_contract_yaml(content)
        if not validation['valid']:
            return jsonify(validation), 400

        # 保存文件
        file_path = CONTRACTS_DIR / filename
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return jsonify({
            'success': True,
            'message': f'Contract {filename} saved successfully',
            'validation': validation
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/contract/<filename>', methods=['DELETE'])
def delete_contract(filename):
    """API: 删除合约"""
    file_path = CONTRACTS_DIR / filename

    if not file_path.exists():
        return jsonify({'error': 'Contract not found'}), 404

    try:
        file_path.unlink()
        return jsonify({
            'success': True,
            'message': f'Contract {filename} deleted successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/contract/new', methods=['POST'])
def create_contract():
    """API: 创建新合约"""
    try:
        filename = request.json.get('filename', '')
        content = request.json.get('content', '')

        if not filename:
            return jsonify({'error': 'Filename is required'}), 400

        if not filename.endswith('.yaml'):
            filename += '.yaml'

        file_path = CONTRACTS_DIR / filename

        if file_path.exists():
            return jsonify({'error': 'Contract already exists'}), 409

        # 验证 YAML
        validation = validate_contract_yaml(content)
        if not validation['valid']:
            return jsonify(validation), 400

        # 保存文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return jsonify({
            'success': True,
            'message': f'Contract {filename} created successfully',
            'filename': filename,
            'validation': validation
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/validate', methods=['POST'])
def validate_contract():
    """API: 验证合约内容（不保存）"""
    try:
        content = request.json.get('content', '')
        validation = validate_contract_yaml(content)
        return jsonify(validation)
    except Exception as e:
        return jsonify({
            'valid': False,
            'error': 'Server Error',
            'message': str(e)
        }), 500


@app.route('/editor')
def editor_page():
    """编辑器页面"""
    filename = request.args.get('file', '')
    return render_template('editor.html', filename=filename)


@app.route('/api/template')
def get_template():
    """API: 获取合约模板"""
    template = {
        'metadata': {
            'contract_id': 'example/new-agent/v1.0.0',
            'version': '1.0.0',
            'status': 'draft',
            'owner_team': 'your-team',
            'created_at': '2026-03-13T00:00:00Z',
            'description': 'New agent contract'
        },
        'intent': {
            'purpose': 'Define the purpose of your agent',
            'scope': 'Define the scope of operations',
            'actions': {
                'allowed': ['action1', 'action2'],
                'restricted': [
                    {
                        'action': 'sensitive_action',
                        'conditions': ['condition1', 'condition2'],
                        'requires_approval': False,
                        'frequency_limit': None
                    }
                ],
                'forbidden': ['dangerous_action']
            }
        },
        'constraints': {
            'hard': [
                {
                    'id': 'example_hard_constraint',
                    'rule': 'field_name <= 1000',
                    'message': 'Field must not exceed 1000'
                }
            ],
            'soft': [
                {
                    'id': 'example_soft_constraint',
                    'rule': 'field_name != ""',
                    'message': 'Field should not be empty'
                }
            ],
            'conditional': [
                {
                    'id': 'example_conditional',
                    'trigger_condition': 'field_name > 100',
                    'then_enforce': {
                        'rule': 'approval_count >= 1',
                        'message': 'Requires approval when field > 100'
                    }
                }
            ],
            'quotas': [
                {
                    'id': 'example_quota',
                    'resource': 'action_count',
                    'limit': 100,
                    'window': 'daily',
                    'scope': 'agent'
                }
            ]
        },
        'drift_detection': {
            'enabled': True,
            'baseline': {
                'metrics': [
                    {
                        'name': 'action_count',
                        'type': 'count',
                        'aggregation_window': '1h'
                    }
                ]
            },
            'thresholds': {
                'action_count': {
                    'warning_at': 50,
                    'critical_at': 80
                }
            },
            'detection_rules': [
                {
                    'metric': 'action_count',
                    'algorithm': 'zscore',
                    'params': {
                        'threshold': 3.0,
                        'min_observations': 10
                    },
                    'on_detect': {
                        'severity': 'warning',
                        'message': 'Unusual action count detected'
                    }
                }
            ],
            'response_playbook': {
                'warning': [
                    {'action': 'log_alert', 'target': 'monitoring_system'}
                ],
                'critical': [
                    {'action': 'require_human_approval'}
                ]
            }
        }
    }

    return jsonify({
        'content': yaml.dump(template, default_flow_style=False, sort_keys=False)
    })


if __name__ == '__main__':
    print("=" * 60)
    print("Guardrail Engine - Contract Editor")
    print("=" * 60)
    print(f"Contracts directory: {CONTRACTS_DIR.absolute()}")
    print(f"Available contracts: {len(get_contract_files())}")
    print("\nStarting web server at http://localhost:5000")
    print("Press Ctrl+C to stop")
    print("=" * 60)

    app.run(debug=True, host='0.0.0.0', port=5000)
