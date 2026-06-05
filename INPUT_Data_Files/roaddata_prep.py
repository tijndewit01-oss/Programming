import pandas as pd

xl_data = pd.ExcelFile('INPUT_Data_Files/ROAD_DATA/SAS_traffic_data.xlsx')

avg_wknd_all = pd.read_excel(xl_data, sheet_name='Table 1 - Avg All', header=2)
avg_wknd2_3 = pd.read_excel(xl_data, sheet_name='Table 2 - Avg Wknd2-3', header=2)
loop_pos = pd.read_excel(xl_data, sheet_name='Detector Positions', header=2)


# avg_wknd_all_detec = avg_wknd_all[['Hour', 'Det1 Saturday', 'Det2 Saturday', 'Det3 Saturday']]
# avg_wknd2_3_detec = avg_wknd2_3[['Hour', 'Det1 Saturday', 'Det2 Saturday', 'Det3 Saturday']]
# loop_coords = loop_pos[['Detector', 'Latitude', 'Longitude']]
# avg_wknd2_3_alldetec = avg_wknd2_3[['Hour', 'Avg Saturday (all det)']]
# avg_wknd_all_alldetec = avg_wknd_all[['Hour', 'Avg Saturday (all det)']]

# avg_wknd_all_detec.to_csv('INPUT_Data_Files/ROAD_DATA/avg_wknd_all_detec.csv', index=False)
# avg_wknd2_3_detec.to_csv('INPUT_Data_Files/ROAD_DATA/avg_wknd2_3_detec.csv', index=False)
# loop_coords.to_csv('INPUT_Data_Files/ROAD_DATA/loop_coords.csv', index=False)
# avg_wknd2_3_alldetec.to_csv('INPUT_Data_Files/ROAD_DATA/avg_wknd2_3_alldetec.csv', index=False)
# avg_wknd_all_alldetec.to_csv('INPUT_Data_Files/ROAD_DATA/avg_wknd_all_alldetec.csv', index=False)

flow_2_3_avg = avg_wknd2_3['Avg Saturday (all det)']
flow_2_3_avg.to_csv('INPUT_Data_Files/ROAD_DATA/flow_2_3_avg.csv', index=False)
