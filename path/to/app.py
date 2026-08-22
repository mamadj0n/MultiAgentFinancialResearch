from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/greet', methods=['POST'])
def greet():
    data = request.get_json()
    name = data.get('name')
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    greeting_message = f"Hey {name}"
    return jsonify({'message': greeting_message}), 200

if __name__ == '__main__':
    app.run(debug=True)
