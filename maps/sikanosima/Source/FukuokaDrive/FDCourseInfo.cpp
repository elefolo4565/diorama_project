#include "FDCourseInfo.h"
#include "EngineUtils.h"

AFDCourseInfo::AFDCourseInfo()
{
	PrimaryActorTick.bCanEverTick = false;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
}

const AFDCourseInfo* AFDCourseInfo::Find(const UWorld* World)
{
	if (World)
	{
		for (TActorIterator<AFDCourseInfo> It(const_cast<UWorld*>(World)); It; ++It)
		{
			return *It;
		}
	}
	return nullptr;
}
