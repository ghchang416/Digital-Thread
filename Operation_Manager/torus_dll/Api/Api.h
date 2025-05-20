#pragma once

#include "ApiLib.h"
#include "controlcmd.h"
#include "item/document.h"
#include <guiddef.h>
#include <string>
#include "ApiCallbackThread.h"

//2024.02.07 HMS
// Added by Sohn,JinHo : 2022.03.04
// --> 
#include <vector>
//#include <hash_map>
#include <unordered_map>
#include "ApiDevComm.h"

//2023.07.13 HMS Lock 추가 getData, updateData st 임시
#include <mutex>

typedef void* ITEM_HANDLE;
typedef void* RPC_SERVER_HANDLE;
typedef void* RPC_CLIENT_HANDLE;
typedef void* API_HANDLE;

typedef int (*callback_function)(int evt, int cmd, const char* command, char** result);
typedef int (*broadcast_function)(const char* command);
//2019-10-08 jsson st
typedef int (*callback_function_data)(int evt, int cmd, const char* command, char** result, void *data);
//2019-10-08 jsson ed

//typedef int (*getDataAsyncCallback_func)(ITEM_HANDLE item);
typedef int (*Callback_Apphotlink)(char* result);


//class FocasApi;
struct _AppHotLinkData;
struct ApphotlinkmapData;

// 2024.08.14 sbc start 프로세스 구조체
struct ProcessInfo;
// sbc ed

/**
@breif Application에서 사용하는 모든 Api를 정의한다.
@mainpage
**/
class INTELIGENT_API CApi
{
private:
	CApi(GUID appID, const char* appName);
	CApi(GUID appID, const char* appName, const char* pFilePath);	// Added by Sohn,JinHo : 2022.03.04

public:
	~CApi(void);

	static CApi* Get(GUID appID, const char* appName);
	static CApi* Get(const char* appID, const char* appName, const char* pMapFilePath);	// Added by Sohn,JinHo : 2024.09.28 
	static CApi* Get(const char* appID, const char* appName);
	static CApi* Get(GUID appID, const char* appName, const char* pMapFilePath);	// Added by Sohn,JinHo : 2022.11.26
	static CApi* Get();

public:
	//FocasApi* focas;
	

public:
	static CApi* initialize(GUID appid, const char* appName);
	static CApi* initialize(const char* appid, const char* appName);

	//Added by cscam : 2024.01.04 TORUS 2.2
	static CApi* initialize(GUID appid, const char* appname, const char* strmapfilepath);

public:
	int initialize();

	int terminate();

	int getData(const char* address, const char* filter, ITEM_HANDLE result, bool direct = true, int timeout = API_TIMEOUT_DEFAULT);
	//int getData(const char* address, const char* filter, double *dData, bool direct = false);
	//double getData2(const char* address, const char* filter,bool direct = false);
	//int getData(const char* address, const char* filter,bool direct = false);

	//21.04.20 hyunwoo
	int getData(const char** address, const char** filter, int arrcnt, ITEM_HANDLE result, bool direct = true, int timeout = API_TIMEOUT_DEFAULT);

	//21.04.21 hyunwoo
	int getData(const char* address, const char* filter, ITEM_HANDLE result, PERIOD_LEVEL level, bool direct = true, int timeout = API_TIMEOUT_DEFAULT);
	int getData(const char** address, const char** filter, int arrcnt, ITEM_HANDLE result, PERIOD_LEVEL level, bool direct = true, int timeout = API_TIMEOUT_DEFAULT);
	int getDataEX(const char* address, const char* filter, ITEM_HANDLE result, PERIOD_LEVEL level, bool bAppHideOperable = false, bool direct = true, int timeout = API_TIMEOUT_DEFAULT);
	int getDataEX(const char** address, const char** filter, int arrcnt, ITEM_HANDLE result, PERIOD_LEVEL level, bool bAppHideOperable = false, bool direct = true, int timeout = API_TIMEOUT_DEFAULT);

	//int getData(getDataItem[] item);
	int updateData(const char* address, const char* filter, ITEM_HANDLE data, ITEM_HANDLE item, int timeout = API_TIMEOUT_DEFAULT);

	//21.04.22 hyunwoo
	int updateData(const char** address, const char** filter, int arrcnt, ITEM_HANDLE data, ITEM_HANDLE item, int timeout = API_TIMEOUT_DEFAULT);
	int updateDataEX(const char* address, const char* filter, ITEM_HANDLE data, ITEM_HANDLE item, bool bAppHideOperable = false, int timeout = API_TIMEOUT_DEFAULT);
	int updateDataEX(const char** address, const char** filter, int arrcnt, ITEM_HANDLE data, ITEM_HANDLE item, bool bAppHideOperable = false, int timeout = API_TIMEOUT_DEFAULT);

	//2021.04.28 HMS st c#과 구조 맞춤.
	//int getDataAsync(const char* address, const char* filter, ITEM_HANDLE result);
	int getDataAsync(const char* address, const char* filter);
	//2021.04.28 HMS ed

	int getDataAsyncResult(const char* address, ITEM_HANDLE result);


	
	//2024.02.06 HMS comment add st TORUS 2.2
	//C# 내용 확인해야 한다.
	// 
	//- GUI App의 로딩 시점을 플랫폼이 확인하는 역할
	//- 통합개발 툴에서는 Code Generation 시에 자동으로 삽입됨
	//- 유지 필요함
	//- 만약 이 함수 없이, 플랫폼이 GUI App의 로딩 시점을 확인할 수 있다면 삭제해도 됨

	void GuiLoaded();

	//2024.02.06 HMS add
	//추후 기능을 추가해 주어야 함. 
	//- GUI를 가진 App의 경우, 종료 시점을 플랫폼이 확인할 수 있는 기능임 
	//(아무것도 안하고 있으면 수정해야 함)
	//(통합 개발 툴에서는 Code generation 시에 자동으로 삽입됨)
	//플랫폼이 이 함수 없이도 GUI App의 종료 시점을 정확히 파악할 수 있다면 삭제해도 됨

	void GuiClosed();

	//2024.02.06 HMS comment add ed TORUS 2.2

	//void ModalFinish(ITEM_HANDLE result);

	int insertData(const char* address, ITEM_HANDLE data, ITEM_HANDLE result, int timeout = API_TIMEOUT_DEFAULT);
	int deleteData(const char* address, ITEM_HANDLE data, ITEM_HANDLE result, int timeout = API_TIMEOUT_DEFAULT);

	int controlApp(int cmd, const char* address, ITEM_HANDLE item, ITEM_HANDLE result, int timeout = API_TIMEOUT_DEFAULT);
	int broadcast(int cmd, ITEM_HANDLE item);

	//2021.04.20 HMS st
	int subscribeData(const char* addr, const char* filter);
	int subscribeDataResult(const char* addr, ITEM_HANDLE data);
	int unsubscribeData(const char* addr, const char* filter);
	int subscribeDataClear();
	//2021.04.20 HMS ed

	//2022.07.15 HMS Object 형태
	//int subscribeData(const char* addr, const char* filter, ITEM_HANDLE obj);
	int subscribeData(const char* addr, const char* filter, int* objectID);// ITEM_HANDLE obj);
	int unsubscribeData(int objectID);

	void regist_callback(int callbackid, callback_function func) {m_callback[callbackid] = func;}

	int getMachinesInfo(ITEM_HANDLE result);

#if 0
	int getPlcSignal(int dataType, const char* plcAddress, ITEM_HANDLE result);
	int setPlcSignal(int dataType, const char* plcAddress, ITEM_HANDLE data, ITEM_HANDLE result);
#else

	//2021.08.12 HMS st machine=0 로 변경, STDAPI 수정시 적용되는 사항. 
    //machine 이 한개만 연결 되어 있을 때는 숫자와 상관없이 연결
    //한개만 연결 되어 있어도 machineList 의 숫자대로 연결 진행 
  // 
	//21.04.22 hyunwoo
	//Fanuc
	int getPlcSignal(FANUC_PLC_TYPE dataType, const char* startAddress, const char* endAddress, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int getPlcSignal(FANUC_PLC_TYPE dataType, const char* startAddress, const char* endAddress, bool direct, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int setPlcSignal(FANUC_PLC_TYPE dataType, const char* startAddress, const char* endAddress, ITEM_HANDLE data, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int setPlcSignal(FANUC_PLC_TYPE dataType, const char* startAddress, const char* endAddress, int* data, int dataCnt, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int setPlcSignal(FANUC_PLC_TYPE dataType, const char* startAddress, const char* endAddress, double* data, int dataCnt, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int setPlcSignal(FANUC_PLC_TYPE dataType, const char* startAddress, const char* endAddress, char** data, int dataCnt, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);

	//Simens
	int getPlcSignal(const char* plcAddress, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int getPlcSignal(const char* plcAddress, bool direct, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int setPlcSignal(const char* plcAddress, ITEM_HANDLE data, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int setPlcSignal(const char* plcAddress, int* data, int dataCnt, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int setPlcSignal(const char* plcAddress, double* data, int dataCnt, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int setPlcSignal(const char* plcAddress, char** data, int dataCnt, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);

	//CSCAM, KCNC, 미쯔비씨
	int getPlcSignal(int dataType, int count, const char* startAddress, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int getPlcSignal(int dataType, int count, const char* startAddress, bool direct, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int setPlcSignal(int dataType, int count, const char* startAddress, ITEM_HANDLE data, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int setPlcSignal(int dataType, int count, const char* startAddress, int* data, int dataCnt, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int setPlcSignal(int dataType, int count, const char* startAddress, double* data, int dataCnt, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int setPlcSignal(int dataType, int count, const char* startAddress, char** data, int dataCnt, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);


#endif

	int getToolOffsetData(int channel, int number, int type, bool direct, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int getToolOffsetData(const char* channel, const char* number, const char* type, bool direct, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);

	//21.04.22 hyunwoo
	int setToolOffsetData(const char* channel, const char* number, const char* type, int* data, int dataCnt, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int setToolOffsetData(const char* channel, const char* number, const char* type, double* data, int dataCnt, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int setToolOffsetData(const char* channel, const char* number, const char* type, char** data, int dataCnt, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int setToolOffsetData(int channel, int number, int type, int* data, int dataCnt, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int setToolOffsetData(int channel, int number, int type, double* data, int dataCnt, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int setToolOffsetData(int channel, int number, int type, char** data, int dataCnt, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);


	int getAttributeExists(const char* path, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int getAttributeType(const char* path, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int getAttributeIsNc(const char* path, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int getAttributeLogicalPath(const char* path, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int getAttributeName(const char* path, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int getAttributePath(const char* path, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int getAttributeSize(const char* path, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int getAttributeEditedTime(const char* path, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int getFileList(const char* path, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);

	//2021.11.25 HMS st file의 정보를 묶어서 가져오는 함수
	int getFileListEx(const char* path, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	//2021.11.25 HMS ed

	int CreateCNCFile(const char* path, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int CreateCNCFolder(const char* path, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int CNCFileRename(const char* path, const char* name, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int CNCFileCopy(const char* source, const char* target, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int CNCFileMove(const char* source, const char* target, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int CNCFileDelete(const char* path, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int CNCFileDeleteAll(const char* path, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int CNCFileExecute(int channel, const char* path, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int CNCFileExecuteExtern(int channel, const char* path, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);

	//2023.02.11 HMS add st
	int CreateCNCFile(const char* parentpath, const char* name, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int CreateCNCFolder(const char* parentpath, const char* name, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	//2023.02.11 HMS add ed
	
	//21.04.22 hyunwoo
	//21.09.16 HMS st Stdapi 에는 구현되어 있으나, DataCode.xml 에 없음,
	//TORUS 1.3 버전 배포시 삭제하여 배포하기로 함. with  손진호 책임. 
	//int ToolLoading(int toolarea, const char* tools, int location, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);

	// data(const char*)를 NC File로 보냅니다.
	int setFileStream(const char* path, const char* data, int machine = 0);

	// NC File을 data(const char*)로 가져옵니다.
	// data는 반드시 delete되어야합니다.

	//21.05.03 hyunwoo st
	int getFileStream(const char* path, int& resLineCount, int machine = 0);
	int getFileStreamData(char** resData);
	//21.05.03 hyunwoo ed
	// NC File을 data(const char*)로 가져옵니다.
	// bufsize만큼만 데이터를 가져옵니다.
	//int getFileStream(const char* data, int bufsize, const char* path);

	// 2019-06-19 추가
	int createTool(int toolArea, int tools, ITEM_HANDLE item, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int deleteTool(int toolArea, int tools, ITEM_HANDLE item, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int loadTool(int toolArea, int tools, int location, ITEM_HANDLE item, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int unloadTool(int toolArea, int tools, ITEM_HANDLE item, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int setPassword(int userAccount, const char* password, ITEM_HANDLE item, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int logInAccount(const char* password, ITEM_HANDLE item, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int logOutAccount(ITEM_HANDLE item, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int selectBlock(int channel, int blockCounter, ITEM_HANDLE item, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int searchBlock(int channel, ITEM_HANDLE item, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	//2023.07.11 HMS st groupGCode  삭제
    //Channel의  전체 Gmodal 코드 정보를 가져오도록 수정함.
	int getGModal(int channel, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	//2021.05.17 HMS st  __ groupGCode 추가
	//2024.02.05 HMS TORUS 2.2 삭제
	//int getExModal(int channel, int groupGCode, const char* modal, ITEM_HANDLE item, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	//2021.05.17 HMS ed

	//2022.02.11 HMS st
	int getExModal(int channel, const char* modal, ITEM_HANDLE result, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	//2022.02.11 HMS ed

	int deleteMDI(int channel, ITEM_HANDLE item, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	
	int setMDIString(int channel, const char* data, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);


	//int getMDIString(int channel, const char** data, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);
	int getMDIString(int channel, int& resLineCount, int machine = 0, int timeout = API_TIMEOUT_DEFAULT);

	//2021.04.16 HMS st 
	int sendLog(const char* msg, ITEM_HANDLE result);
	int sendLogEx(const char* msg, ITEM_HANDLE result, int loglevel);
	int setLanguage(int language, ITEM_HANDLE result);
    //2021.04.16 HMS ed
    //2021.04.19 HMS st
	int registTimeSeries(const char* address, const char* filter, ITEM_HANDLE result);
	int unregistTimeSeries(const char* address, const char* filter);

	int DeliveryFile(const char* appname, const char* path, int timeout = API_TIMEOUT_DEFAULT);

	//2021.04.28 HMS st machine=1 로 변경 , 04.30 HMS st channel 추가
    //2022.07.22 HMS timeout 변경
	//Timeout 오류가 반환된 이후에도 STDAPI에서 프로세스가 종료되지 않고 진행이 정상적으로 완료됨.
	//STDAPI까지 grpc cancel을 전달할 수 있는 방법이 없음으로 Timeout 시간을 연장하기로 함. 
	int UploadFile(const char* local_path, const char* nc_path, int machine = 0, int channel = 1, int timeout = 60000);//API_TIMEOUT_DEFAULT);
	int DownloadFile(const char* nc_path, const char* local_path, int machine = 0, int channel = 1, int timeout = 60000);//API_TIMEOUT_DEFAULT);
	//2021.04.28 HMS ed

	void setSiemenseLibPath(const char* path);
	const char* getSiemenseLibPath();

	//2021.04.20 HMS ed

	//2022.03.04 HMS st gud 값 operation 함수 추가
	//2024.02.06 HMS st 함수 하나만 유지

	//int getGudData(GUD_TYPE dataType, int number, int count, const char* address, ITEM_HANDLE result, int machine = 0, int channel = 1, int timeout = API_TIMEOUT_DEFAULT);
	int getGudData(GUD_TYPE dataType, int number, int count, const char* address, bool direct, ITEM_HANDLE result, int machine = 0, int channel = 1, int timeout = API_TIMEOUT_DEFAULT);

	int setGudData(GUD_TYPE dataType, int number, int count, const char* address, ITEM_HANDLE data, ITEM_HANDLE result, int machine = 0, int channel = 1, int timeout = API_TIMEOUT_DEFAULT);
	int setGudData(int number, int count, const char* address, double* data, ITEM_HANDLE result, int machine = 0, int channel = 1, int timeout = API_TIMEOUT_DEFAULT);
	int setGudData(int number, int count, const char* address, char** data, ITEM_HANDLE result, int machine = 0, int channel = 1, int timeout = API_TIMEOUT_DEFAULT);

	//2022.03.04 HMS ed

	void AddTraceMsg(int level, const char* szMessage);

	//2024.06.24 HMS 시계열 데이터 기능 함수
	//startofstream, endofstream

	int startTimeSeries(int buffer, int machine = 0, int timeout = API_TIMEOUT_BUFFER);
	int endTimeSeries(int buffer, int machine = 0, int timeout = API_TIMEOUT_BUFFER);

	//EdgeData
	int startEdgeData(int edgedevice = 1, int channel = 1, int timeout = API_TIMEOUT_BUFFER);
	int endEdgeData(int edgedevice = 1, int channel = 1, int timeout = API_TIMEOUT_BUFFER);

	//내부 사용 함수
public:

	void shown();	// gui가 실행됨.

	//2020.01.06 HMS App singletone 오류 check 추가
	int guishown();

	int command(const char* command, char** result);
	//2020-02-04 jsson st
	int command(const char* command, int arrcnt, char** result);
	//2020-02-04 jsson ed

	//2021.04.26 HMS st _ grpc Timeout 추가
	int command(const char* command, char** result, int timeout);
	int command(const char* command, int arrcnt, int timeout, char** result);
	//2021.04.26 HMS ed 

	int subscribeData(const char* addr, callback_function observer);
	int unsubscribeData(callback_function observer);

	void OnBroadCast(const char* cmd);
	void broadcast_callback(int id, broadcast_function func) { m_broadcast_callback[id] = func; }

	//2019-10-08 jsson st
	void regist_callback_data(callback_function_data func) { m_callbackData = func; }
	//2019-10-08 jsson ed

	//c#은 directcallback으로만 넘어가는것 같음. hyunwoo
	void regist_directcallback(callback_function func) { m_directcallback = func; }

	//2020-03-10 jsson st
	void callback_thread(const std::string tname, int num);
	//2020-03-10 jsson ed

	int updateHotLinkData(const char* paramname, ITEM_HANDLE data);
	int updateHotLinkDataProc(const char* paramname, const char* data);

	//2021.07.28 HMS st
	void OnHotLinkCompare();
	int regAppHotLink(const char* address);
	void AppHotLinkData_callback(Callback_Apphotlink func) { m_appHotlink_callbback = func; };
	//

	//2022.10.06 HMS st
	void OnAsyncDataResult();

#if false
	//2021.08.11 HMS st
	int Reset(MANAGERINFO mgrinfo);
	int Reconnection();
	//2021.08.11 HMS ed

#endif

public: // callback event
	static int callback(const unsigned char *cmd,unsigned char **result);


protected:

	int updateData(const char* address, const char* filter, const char* data, ITEM_HANDLE resultItem, int timeout = API_TIMEOUT_DEFAULT);

	int getDataProc(const char* address, const char* filter, ITEM_HANDLE result, bool direct, bool bAppHideOperableOption, PERIOD_LEVEL periodLv, int timeout);
	int getDataArrayProc(const char** address, const char** filter, int arrcnt, ITEM_HANDLE result, bool direct, bool bAppHideOperableOption, PERIOD_LEVEL periodLv, int timeout);

	int updateDataProc(const char* address, const char* filter, ITEM_HANDLE data, ITEM_HANDLE resultItem, bool bAppHideOperable, int timeout);
	int updateDataProc(const char* address, const char* filter, const char* data, ITEM_HANDLE resultItem, bool bAppHideOperable, int timeout);
	int updateDataArrayProc(const char** address, const char** filter, int arrcnt, ITEM_HANDLE data, ITEM_HANDLE resultItem, bool bAppHideOperable, int timeout);

	void RegistCallbackThreadFunc();

	//2021.07.28 HMS st
	
	void OnRegistAppHotLinkData(ApphotlinkmapData* mapdata);
	bool AppcheckProc();

	//2024.08.14 sbc 실행중인 프로세스 내 매니저 조회 및 포트확인
	//static unsigned long FindProcessId(const string& processName);
	//static int GetProcessPort(unsigned long pid);

public: // property
	const char* appName(){return m_appName;}
	GUID appID(){return m_appID;}
	int executeIndex(){return m_executeIndex;}
	GUID executeID(){return m_executeID;}
	void executeIDString(char* result);
	RPC_CLIENT_HANDLE getClient(){return m_rpcClient;}
	
	//ANSI
	int lastResultSize();
	const char* lastResult();

	int callbackResultSize();

	//2020-02-04 jsson st
	int lastResultSize(int idx);
	const char* lastResult(int idx);
	//2020-02-04 jsson ed

	//2023.07.18 HMS .net 5.0 이상은 UTF8 이 기준 
	//encoding ANSI->UTF8관련
	int lastResultSizeUTF8();
	char* lastResultUTF8();

	//2020-02-04 jsson st
	int lastResultSizeUTF8(int idx);
	char* lastResultUTF8(int idx);
	//2020-02-04 jsson ed


	bool AppStop(){return m_appstop;}

	int iSwapFilterAddrData(char* pChFilterData);		// Added by Sohn,JinHo : 2022.12.26
	int iSwapPLCFilterAddrData(char* pChFilterData);	// Added by Sohn,JinHo : 2024.08.02
	int iSwapPLCFilterAddrData(char* pChFilterData, char* pOutFilterData);	// Added by Sohn,JinHo : 2024.08.02

private:
	static CApi* m_api;

	std::mutex getDataProc_mutex;
	std::mutex updateDataProc_mutex;
	
	GUID m_appID;
	char m_appName[1024];
	int m_executeIndex;
	GUID m_executeID;

	callback_function m_callback[CALLBACK_MAX];
	callback_function m_directcallback;
	broadcast_function m_broadcast_callback[BROADCAST_MAX];
	//2019-10-08 jsson st
	callback_function_data m_callbackData;
	//2019-10-08 jsson ed

	RPC_SERVER_HANDLE m_rpcServer;
	RPC_CLIENT_HANDLE m_rpcClient;

	char* m_lastResult;
	//2020-02-04 jsson st
	char** m_lastResultArr;
	int		  m_lastResultArrCnt;
	//2020-02-04 jsson ed
	bool m_appstop;

	//21.04.23 hyunwoo
	callback_thread_function m_callbackThread[CALLBACK_MAX];

	CApiDevComm m_DevCommApi; // Added by Sohn,JinHo : 2022.11.26
	// Added by Sohn,JinHo : security manager Function
	char m_streamFilePath[256];

	//2021.07.28 HMS st
	Callback_Apphotlink  m_appHotlink_callbback;

	//Callback_AsyncDataResult m_AsyncDataresult_callback;	

	//2024.06.25 HMS
	int m_callbackResultsize;

private:
	//2022.010.06 HMS asyncdata event 결과 반환용 
	int getDataAsyncResult(const char* address, const char* result);


};
