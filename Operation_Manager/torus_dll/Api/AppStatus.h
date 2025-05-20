#pragma once

#include "ApiLib.h"
#include <guiddef.h>

struct MapAppStatus;

// 공유메모리 접근 API
class INTELIGENT_API CAppStatus
{
public:
	CAppStatus(MapAppStatus* ptr);
	CAppStatus(const char* name);
	CAppStatus(int exeindex);
	~CAppStatus();

public: // public method
	const char* Name();
	bool Initialized();
	bool Executing();
	GUID ExecuteID();
	int ExecuteIndex();
	// cpu 사용량 : %
	double CPU();
	// 메모리 사용량 MB
	double RAM();

public: // static method
	static int GetExeuteAppCount();
	static CAppStatus* GetExeuteApp(int exeindex);

private:
	void SetMap(MapAppStatus* ptr);

private:
	MapAppStatus* m_map;
};

typedef void* APPSTATUS;
//
//#ifdef __cplusplus
//extern "C"{
//#endif
//
//INTELIGENT_API int AppStatus_GetExeuteAppCount();
//INTELIGENT_API APPSTATUS AppStatus_GetExeuteApp(int exeindex);
//INTELIGENT_API const char* AppStatus_Name(APPSTATUS app);
//INTELIGENT_API int AppStatus_Initialized(APPSTATUS app);
//INTELIGENT_API int AppStatus_Executing(APPSTATUS app);
//INTELIGENT_API GUID AppStatus_ExecuteID(APPSTATUS app);
//INTELIGENT_API int AppStatus_ExecuteIndex(APPSTATUS app);
//INTELIGENT_API double AppStatus_CPU(APPSTATUS app);
//INTELIGENT_API double AppStatus_RAM(APPSTATUS app);
//
//#ifdef __cplusplus
//}
//#endif