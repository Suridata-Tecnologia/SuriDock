from extensions.google_cloud import GoogleFirestore



database = GoogleFirestore().get_all_jobs()
status_to_delete = ['failed', 'cancelled', 'completed']
jobs_to_delete = []

for data in database:
    if database[data]['status'] in status_to_delete:
        jobs_to_delete.append(data)


if jobs_to_delete:
    delete_count = GoogleFirestore().delete_jobs_batch(jobs_to_delete)
else:
    delete_count = 0

print(f'{delete_count} jobs excluídos')
