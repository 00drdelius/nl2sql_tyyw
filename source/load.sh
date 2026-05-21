sqls_dir=/home/gmcc/workspace/text2sql-projects/tongyiyunwei/AI_Query_System/fastapi_server/source/test-attendance-db


test_loop(){
    for i in {0..9}; do echo $i; done
}
# test_loop

test_find_loop(){
    for i in `find $sqls_dir -type f -name "*.sql"`; do echo $i; done
}

# test_find_loop

exec_sql_loop(){
    for sql_file in `find $sqls_dir -type f -name "*.sql.d"`;
        do psql -U postgres -d public -f $sql_file;
        echo "$sql_file done, jump to next..."
    done

}

exec_sql_loop