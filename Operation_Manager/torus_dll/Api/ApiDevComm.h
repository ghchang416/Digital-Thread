// Created by Sohn,JinHo : 2022.11.26

#pragma once

#include "ApiLib.h"

#include <string>
#include <vector>
#include <unordered_map>

#define MAX_STRING_SIZE	1024	// added by Sohn,JinHo: 2023.02.27

using namespace std;

/// <summary>
/// 
/// </summary>
enum DATATYPE
{
	INBITBLOCK	= 1,
	BITBLOCK	= 2,
	INBYTEBLOCK = 3,
	BYTEBLOCK	= 4,
	INWORDBLOCK = 5,
	WORDBLOCK	= 6,
	INDWORDBLOCK= 7,
	DWORDBLOCK	= 8,
	INQWORDBLOCK= 9,
	QWORDBLOCK	= 10
};

typedef struct
{
	std::string strFilterName;
	int iFilterValue;
}DevCommFilterInfo;

/// <summary>
/// Added by Sohn,JinHo : 2022.11.26
/// </summary>
typedef struct
{
	std::string strMemID;			// Platform Memory ID
	std::string strMemBlock;		// Platform memory block to be mapped with external device PLC memory
	std::string strDataAddress;		// Data address in platform memory block to be mapped with external device PLC memory
	std::string strDevID;			// 
	std::string strDevMemType;		// Device user name
	std::string strDevTargetAdde;	// Password for login the device
	std::string strDescription;		// extern path for device network protocol lib
} DevMemInfo;

/// <summary>
/// Added by Sohn,JinHo : 2024.08.02
/// The data model for NC interal PLC 
/// </summary>
typedef struct
{
	std::string strMachineID;		// Machine ID of NC internal PLC
	std::string strVendorCode;		// NC/PLC Vendor code
	std::string strDataType;		// 
	std::string strPLCTargetAddress;// Target PLC data address in PLC
	std::string strMemID;			// Platform Memory ID
	std::string strMemBlockType;	// Platform memory block type to be mapped with NC internal PLC memory	
	std::string strDataAddress;		// Data address in platform memory block to be mapped with NC internal PLC memory
	std::string strDescription;		// extern path for device network protocol lib
} PLCMemInfo;

/// <summary>
/// Added by Sohn,JinHo : 2022.11.26
/// </summary>
typedef struct
{
	std::string strDevID;
	std::string strMemType;
	std::string strTargetAddr;
	std::string strDesc;
}DevCommAddrInfo;

/// <summary>
/// Added by Sohn,JinHo : 2024.08.02
/// The address information for NC internal PLC 
/// </summary>
typedef struct
{
	std::string strMemID;
	std::string strMemBlkType;
	std::string strPLCDataAddr;
	std::string strMachineID;
	std::string strVendorCode;
	std::string strTargetDataType;
	std::string strPLCTargetAddr;
	std::string strPLCTargetEndAddr;
	std::string strDesc;
} PLCCommAddrInfo;

class INTELIGENT_API CApiDevComm
{
public: 
	CApiDevComm();

	int LoadMemMappingFile(char* pMpFeilPath);				// Added by Sohn,JinHo : 2024.08.02
	//int LoadDevMemInfoFile(char* pFilePath);				//
	int LoadDevMemInfoFile(std::string mapfilePath);		// Modified by SOhn,JinHo : 2024.08.02
	int LoadPlcMemInfoFile(std::string mapfilePath);		// Added by Sohn,JinHo : 2024.08.02

	int swapDevCommAddr(std::string& strFilter);			// 
	int swapDevCommAddr(char* strFilter);

	int swapPLCCommAddr(char* pChFilter);					// Added by Sohn,JinHo : 2024.08.02
	int swapPLCCommAddr(char* pChFilter, char* pOurFilterData);					// Added by Sohn,JinHo : 2024.08.02
	
	int initMapFilePath(const char* pFilePath);				// 
	void setDecCommFlag(bool bSetValue);					// 
	void setPlcCommFlag(bool bSetValue);

	vector<std::string> TrSplit(std::string str, char chSpt);	// added by Sohn,JinHo : 2024.08
	string ToLowercase(std::string strVal);						// added by Sohn,JinHo : 2024.08

	
private:
	int pDelSpaceinStr(const char* pInCh, char* pOutCh);	// 
	bool isOnlyNumber(const std::string& str);				// 		
	int searchMemBlock(const char* pChStr);

	//string ToLowercase(std::string strVal);						// added by Sohn,JinHo : 2024.08

	std::vector<DevMemInfo> m_DevInfoList;
	std::unordered_map<std::string, DevCommAddrInfo> m_DevMapTable;
	std::unordered_map<std::string, PLCCommAddrInfo> m_PLCMapTable;

	bool m_bFlagFieldBusComm;			
	bool m_bFlagPLCComm;
	char m_MemMapFilePath[MAX_STRING_SIZE];

	std::vector<DevCommFilterInfo> m_CommFilterInfoList;

};