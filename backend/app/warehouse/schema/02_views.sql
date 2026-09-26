CREATE OR REPLACE VIEW v_customers_masked AS
SELECT customer_id,
       full_name,
       regexp_replace(email, '^[^@]+', '***') AS email,
       '***' || right(phone, 3)               AS phone,
       city,
       region_id,
       segment,
       signup_date
FROM customers;

CREATE OR REPLACE VIEW v_employees_masked AS
SELECT employee_id, full_name, store_id, position, hired_on
FROM employees;
