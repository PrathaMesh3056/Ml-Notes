# Testing APIs \& Serverless Computing (AWS Lambda)

\---

## Table of Contents

1. [Testing APIs with FastAPI \& pytest](#1-testing-apis-with-fastapi--pytest)
2. [AWS Lambda - Serverless Computing](#2-aws-lambda---serverless-computing)
3. [Git Commit](#git-commit)

\---

## 1\. Testing APIs with FastAPI \& pytest

### 1.1 Introduction to API Testing

Testing ensures your API endpoints work correctly before deployment. FastAPI provides `TestClient` to simulate HTTP requests without running a real server.

**Why test APIs?**

* Catch bugs early
* Ensure endpoints return correct data
* Validate error handling
* Maintain code quality during refactoring

\---

### 1.2 Basic TestClient Pattern

`TestClient` simulates HTTP requests to your FastAPI app without starting a real server.

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()

@app.get("/users")
def get\_users():
    return {"users": \["Alice", "Bob"]}

# Create test client
client = TestClient(app)

def test\_get\_users():
    response = client.get("/users")
    assert response.status\_code == 200
    assert response.json() == {"users": \["Alice", "Bob"]}
```

**Key Methods:**

* `client.get(url)` - GET request
* `client.post(url, json=data)` - POST request
* `client.put(url, json=data)` - PUT request
* `client.delete(url)` - DELETE request

**Response Object:**

* `response.status\_code` - HTTP status code (200, 404, etc.)
* `response.json()` - Parse JSON response
* `response.text` - Raw text response
* `response.headers` - Response headers

\---

### 1.3 pytest Fixtures

Fixtures are reusable setup/teardown code that runs before and after tests.

#### Basic Fixture Pattern

```python
import pytest

@pytest.fixture
def sample\_data():
    # SETUP: runs before test
    data = {"name": "Alice", "age": 30}
    
    yield data  # Test runs here and receives this data
    
    # TEARDOWN: runs after test
    print("Cleaning up after test")

def test\_user\_data(sample\_data):
    # sample\_data is automatically injected
    assert sample\_data\["name"] == "Alice"
    assert sample\_data\["age"] == 30
```

**How it works:**

1. pytest sees `sample\_data` parameter in test function
2. Finds the `@pytest.fixture` with matching name
3. Runs setup code before `yield`
4. Test receives the yielded value
5. Test runs
6. Teardown code runs after `yield`

\---

### 1.4 Testing with Database

**The Problem:** Production database shouldn't be used for tests.

**Solution:** Use a test database with fixture-based dependency override.

#### Complete Database Testing Pattern

```python
# main.py
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

app = FastAPI()

# Production database dependency
def get\_db():
    db = SessionLocal()  # Production database
    try:
        yield db
    finally:
        db.close()

@app.get("/users")
def get\_users(db: Session = Depends(get\_db)):
    users = db.query(User).all()
    return {"users": \[user.name for user in users]}

@app.post("/users")
def create\_user(name: str, db: Session = Depends(get\_db)):
    user = User(name=name)
    db.add(user)
    db.commit()
    return {"id": user.id, "name": user.name}
```

```python
# test\_main.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create\_engine
from sqlalchemy.orm import sessionmaker
from main import app, get\_db, Base

# 1. Create test database (SQLite in-memory for speed)
TEST\_DATABASE\_URL = "sqlite:///./test.db"
engine = create\_engine(
    TEST\_DATABASE\_URL,
    connect\_args={"check\_same\_thread": False}
)
TestingSessionLocal = sessionmaker(bind=engine)

# 2. Fixture: Override database dependency
@pytest.fixture
def client():
    # SETUP: Create tables
    Base.metadata.create\_all(bind=engine)
    
    # Override get\_db to use test database
    def override\_get\_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()
    
    app.dependency\_overrides\[get\_db] = override\_get\_db
    
    # Create test client
    test\_client = TestClient(app)
    yield test\_client
    
    # TEARDOWN: Drop tables after test
    Base.metadata.drop\_all(bind=engine)

# 3. Use fixture in tests
def test\_create\_user(client):
    # Create user
    response = client.post("/users", json={"name": "Alice"})
    assert response.status\_code == 201
    assert response.json()\["name"] == "Alice"
    
    # Verify user exists
    response = client.get("/users")
    assert len(response.json()\["users"]) == 1

def test\_get\_empty\_users(client):
    response = client.get("/users")
    assert response.status\_code == 200
    assert response.json()\["users"] == \[]
```

**Key Concepts:**

* `app.dependency\_overrides\[get\_db]` - Replaces production dependency with test version
* `Base.metadata.create\_all()` - Creates all tables before test
* `Base.metadata.drop\_all()` - Drops all tables after test
* Each test gets a fresh database

\---

### 1.5 Common Testing Patterns

#### Testing POST Requests

```python
def test\_create\_user(client):
    response = client.post(
        "/users",
        json={"name": "Alice", "email": "alice@example.com"}
    )
    assert response.status\_code == 201
    assert response.json()\["name"] == "Alice"
    assert "id" in response.json()
```

#### Testing Authentication

```python
def test\_protected\_endpoint\_without\_token(client):
    response = client.get("/protected")
    assert response.status\_code == 401
    assert response.json()\["detail"] == "Unauthorized"

def test\_protected\_endpoint\_with\_token(client):
    response = client.get(
        "/protected",
        headers={"Authorization": "Bearer valid-token"}
    )
    assert response.status\_code == 200
```

#### Testing Error Cases

```python
def test\_create\_user\_invalid\_email(client):
    response = client.post(
        "/users",
        json={"name": "Alice", "email": "invalid-email"}
    )
    assert response.status\_code == 422  # Validation error
    assert "email" in response.json()\["detail"]\[0]\["loc"]

def test\_get\_nonexistent\_user(client):
    response = client.get("/users/99999")
    assert response.status\_code == 404
    assert response.json()\["detail"] == "User not found"
```

#### Fixtures for Test Data

```python
@pytest.fixture
def sample\_user(client):
    """Create a user and return its data"""
    response = client.post("/users", json={"name": "Alice"})
    return response.json()

def test\_get\_user\_by\_id(client, sample\_user):
    user\_id = sample\_user\["id"]
    response = client.get(f"/users/{user\_id}")
    assert response.status\_code == 200
    assert response.json()\["name"] == "Alice"

def test\_delete\_user(client, sample\_user):
    user\_id = sample\_user\["id"]
    response = client.delete(f"/users/{user\_id}")
    assert response.status\_code == 204
    
    # Verify user is deleted
    response = client.get(f"/users/{user\_id}")
    assert response.status\_code == 404
```

\---

### 1.6 Testing Async Endpoints

For async endpoints, use `pytest-asyncio` with `AsyncClient`.

```python
import pytest
from httpx import AsyncClient
from main import app

@pytest.mark.asyncio
async def test\_async\_endpoint():
    async with AsyncClient(app=app, base\_url="http://test") as client:
        response = await client.get("/async-users")
        assert response.status\_code == 200
```

\---

### 1.7 Best Practices

|Practice|Recommendation|
|-|-|
|**Isolation**|Each test should be independent (no shared state)|
|**Database**|Use in-memory SQLite for speed, or separate test DB|
|**Fixtures**|Use fixtures for common setup (test data, clients)|
|**Naming**|Name tests clearly: `test\_create\_user\_success`, `test\_create\_user\_invalid\_email`|
|**Coverage**|Test success cases, error cases, edge cases|
|**Fast tests**|Keep tests fast (under 1 second each)|
|**Cleanup**|Always clean up after tests (drop tables, delete files)|

\---

## 2\. AWS Lambda - Serverless Computing

### 2.1 What is AWS Lambda?

AWS Lambda is a **serverless compute service** that runs your code in response to events without managing servers.

**Traditional Server vs Lambda:**

|**Traditional Server (EC2)**|**AWS Lambda (Serverless)**|
|-|-|
|Rent/manage server 24/7|No server management|
|Server runs constantly (costs even when idle)|Runs only when triggered|
|You handle scaling, updates, patches|AWS handles everything|
|Pay for uptime|Pay per execution (100ms increments)|
|Good for constant workloads|Good for event-driven tasks|

\---

### 2.2 When to Use Lambda

✅ **Good Use Cases:**

* **Event-driven tasks** - Image processing on S3 upload, send email on order
* **Infrequent workloads** - Runs once/day or once/week
* **APIs with variable traffic** - Auto-scales from 0 to thousands
* **Background jobs** - Data processing, report generation, cleanup
* **Microservices** - Small, independent functions

❌ **NOT Recommended:**

* **Long-running tasks** - Lambda has 15-minute timeout
* **Persistent connections** - WebSockets, database pools
* **Predictable high-frequency load** - Traditional server cheaper if running 24/7
* **Large applications** - Lambda has 250MB package size limit (50MB zipped)

\---

### 2.3 How Lambda Works

```
Event triggers Lambda
    ↓
AWS spins up function (cold start \~100ms-1s)
    ↓
Your Python code runs
    ↓
Function returns result
    ↓
AWS shuts down function
    ↓
You pay only for execution time
```

**Pricing:**

* First 1 million requests/month: FREE
* After that: $0.20 per 1 million requests
* Execution time: $0.0000166667 per GB-second

**Example:** 1 million requests, 128MB memory, 200ms execution each:

* Requests: FREE (under 1M)
* Compute: \~$0.42
* **Total: \~$0.42/month**

\---

### 2.4 Creating Your First Lambda Function

#### Step 1: Create Function in AWS Console

1. Go to AWS Console → Search "Lambda"
2. Click "Create function"
3. Choose "Author from scratch"
4. Function name: `string\_reversal`
5. Runtime: Python 3.13
6. Click "Create function"

#### Step 2: Write Lambda Handler

```python
import json

def lambda\_handler(event, context):
    """
    Lambda function entry point
    
    Args:
        event (dict): Input data passed to function
        context (object): Lambda runtime information
    
    Returns:
        dict: Response with statusCode and body
    """
    # Get input from event
    string = event.get('string', '')
    
    if not string:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'String is required'})
        }
    
    # Reverse the string
    reversed\_string = string\[::-1]
    
    # Return response
    return {
        'statusCode': 200,
        'body': json.dumps({
            'original': string,
            'reversed': reversed\_string
        })
    }
```

#### Step 3: Test in Console

1. Click "Test" tab
2. Create new event: `{"string": "NeuralNine"}`
3. Click "Test"
4. View output: `{"original": "NeuralNine", "reversed": "eniNlarueN"}`

\---

### 2.5 Invoking Lambda with Python (boto3)

#### Setup AWS CLI

```bash
# Install AWS CLI
# Linux/Mac:
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86\_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Windows: Download installer from aws.amazon.com/cli

# Configure with your credentials
aws configure
# AWS Access Key ID: \[your key]
# AWS Secret Access Key: \[your secret]
# Default region: eu-central-1 (or your region)
# Default output format: json
```

**Getting Access Keys:**

1. AWS Console → Your Account → Security Credentials
2. Create access key
3. Save Access Key ID and Secret Access Key

#### Install boto3

```bash
pip install boto3\[crt]
```

#### Invoke Lambda from Python

```python
import json
import boto3

# Create Lambda client (uses AWS CLI credentials automatically)
client = boto3.client('lambda')

# Invoke function
response = client.invoke(
    FunctionName='string\_reversal',
    Payload=json.dumps({
        'string': 'NeuralNine'
    })
)

# Read response
result = response\['Payload'].read()
print(json.loads(result))
# Output: {'statusCode': 200, 'body': '{"original": "NeuralNine", "reversed": "eniNlarueN"}'}
```

\---

### 2.6 Lambda with Multiple Operations - Calculator Example

```python
import json

def lambda\_handler(event, context):
    # Get inputs
    num1 = event.get('number1')
    num2 = event.get('number2')
    operation = event.get('operation')
    
    # Validate inputs
    if num1 is None or num2 is None or operation is None:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Missing required parameters'})
        }
    
    try:
        num1 = float(num1)
        num2 = float(num2)
    except ValueError:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Invalid number format'})
        }
    
    # Perform operation
    match operation:
        case 'add':
            result = num1 + num2
        case 'subtract':
            result = num1 - num2
        case 'multiply':
            result = num1 \* num2
        case 'divide':
            if num2 == 0:
                return {
                    'statusCode': 400,
                    'body': json.dumps({'error': 'Division by zero'})
                }
            result = num1 / num2
        case \_:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid operation'})
            }
    
    return {
        'statusCode': 200,
        'body': json.dumps({'result': result})
    }
```

**Invoke from Python:**

```python
response = client.invoke(
    FunctionName='simple\_calculator',
    Payload=json.dumps({
        'number1': 10,
        'number2': 5,
        'operation': 'multiply'
    })
)

result = json.loads(response\['Payload'].read())
print(result)  # {'statusCode': 200, 'body': '{"result": 50}'}
```

\---

### 2.7 Integrating Lambda with S3

Lambda can interact with other AWS services like S3 (storage).

#### Example: Upload File to S3 Bucket

**Step 1: Create S3 Bucket**

1. AWS Console → S3
2. Create bucket: `my-lambda-fancy-bucket`
3. Leave default settings

**Step 2: Lambda Function with S3**

```python
import json
import base64
import boto3

def lambda\_handler(event, context):
    # Create S3 client
    s3\_client = boto3.client('s3', region\_name='eu-central-1')
    
    # Get file data from event
    file\_name = event.get('file\_name')
    file\_content = event.get('file\_content')  # Base64 encoded
    
    if not file\_name or not file\_content:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Missing file\_name or file\_content'})
        }
    
    try:
        # Decode base64 file content
        file\_content = base64.b64decode(file\_content)
        
        # Upload to S3
        s3\_client.put\_object(
            Bucket='my-lambda-fancy-bucket',
            Key=file\_name,
            Body=file\_content
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'File uploaded successfully'})
        }
    
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
```

**Step 3: Python Script to Upload**

```python
import json
import base64
import boto3

client = boto3.client('lambda')

# Read file
with open('example.txt', 'rb') as file:
    file\_content = base64.b64encode(file.read()).decode('utf-8')

# Invoke Lambda
response = client.invoke(
    FunctionName='S3\_Lambda\_integration',
    Payload=json.dumps({
        'file\_name': 'uploaded\_example.txt',
        'file\_content': file\_content
    })
)

result = json.loads(response\['Payload'].read())
print(result)  # {'statusCode': 200, 'body': '{"message": "File uploaded successfully"}'}
```

**Step 4: Fix Permissions (IAM Role)**

If you get "Access Denied" error:

1. AWS Console → IAM → Roles
2. Create new role → AWS Service → Lambda
3. Add permission: `AmazonS3FullAccess`
4. Role name: `Lambda\_S3\_Permission\_Role`
5. Create role
6. Go to Lambda → Configuration → Permissions
7. Edit execution role → Select `Lambda\_S3\_Permission\_Role`
8. Save

\---

### 2.8 Lambda Triggers

Lambda functions can be triggered by various AWS events:

|**Trigger**|**Use Case**|**Example**|
|-|-|-|
|**S3 Event**|File uploaded to bucket|Process image when uploaded|
|**API Gateway**|HTTP request to API|RESTful API endpoint|
|**CloudWatch Events**|Scheduled (cron)|Run report every night at 2 AM|
|**DynamoDB Stream**|Database change|Update cache when record changes|
|**SNS/SQS**|Message published|Process queue messages|
|**Manual (boto3)**|Direct invocation|Call from your Python app|

#### Example: S3 Trigger Setup

1. Lambda → Configuration → Triggers
2. Add trigger → S3
3. Select bucket
4. Event type: `PUT` (when file uploaded)
5. Save

Now when any file is uploaded to that bucket, Lambda runs automatically.

\---

### 2.9 Lambda Limitations

|**Limit**|**Value**|
|-|-|
|Execution timeout|15 minutes max|
|Memory|128 MB to 10 GB|
|Package size|250 MB unzipped, 50 MB zipped|
|/tmp storage|10 GB|
|Concurrent executions|1000 (default, can request increase)|
|Environment variables|4 KB total|

\---

### 2.10 Best Practices

✅ **Do:**

* Keep functions small and focused (single responsibility)
* Use environment variables for configuration
* Handle errors gracefully with try/except
* Use IAM roles with least privilege (only permissions needed)
* Monitor with CloudWatch Logs
* Keep dependencies minimal (faster cold starts)

❌ **Don't:**

* Store sensitive data in code (use AWS Secrets Manager)
* Use Lambda for long-running tasks (>15 min)
* Create global database connections (use connection pooling)
* Ignore cold start times (first invocation slower)

\---

### 2.11 Lambda + FastAPI Integration Example

You can use Lambda to handle specific tasks while your main API runs on a server.

```python
# FastAPI application
from fastapi import FastAPI
import boto3
import json

app = FastAPI()
lambda\_client = boto3.client('lambda')

@app.post("/process-image")
async def process\_image(image\_url: str):
    # Offload image processing to Lambda
    response = lambda\_client.invoke(
        FunctionName='image\_processor',
        Payload=json.dumps({'image\_url': image\_url})
    )
    
    result = json.loads(response\['Payload'].read())
    return {"status": "processing", "result": result}
```

This pattern lets you:

* Keep API fast (offload heavy work)
* Scale automatically (Lambda handles spikes)
* Pay only for processing time

\---

**End of Document**

