To run the project, first create virtual environment with

```virtualenv venv -p [path]```

where `[path]` is the path to your Python3 installation (e.g. /usr/bin/python3).

Next, install project requirements using the following command

```venv/bin/pip3 install -r requirements.txt```


After the installation is done you can finally run the application.

Use `venv/bin/python3 fetch_data.py` in order to populate the database.

Enter `venv/bin/python3 app.py` to initiate the application.

You also need to install binaries needed to generate the pdf files
On debian based distro run
sudo apt-get install wkhtmltopdf

App will be accessible under the URL localhost:8050.

-----------------------------------------------

The app requires a local PostgreSQL instance running on port 5432.

The credentials should be io_user:io_password for a database named io_database.

You can create required user and database by running the following commands:

`sudo su postgres`

`psql`

`CREATE USER io_user ENCRYPTED PASSWORD 'io_password' LOGIN CREATEDB;`

`\q`

ctrl+D

`psql postgresql://io_user:io_password@localhost/postgres`

`CREATE DATABASE io_database;`

`\q`



