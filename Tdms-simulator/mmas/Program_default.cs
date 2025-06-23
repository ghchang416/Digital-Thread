using System;
using System.Net.Http;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Grpc.Net.Client;
using TdmsService;
using Microsoft.Extensions.Logging;

namespace Simulator
{
    class Program
    {
        // gRPC 서버 주소 및 ISO API 서버 주소 (컨테이너 네트워크 기준)
        private const string grpcServer = "http://grpc:50051";
        private const string apiServer = "http://app:8000"; // ISO api 서버 address

        static async Task Main(string[] args)
        {
            // 콘솔 로거 설정
            var loggerFactory = LoggerFactory.Create(builder =>
            {
                builder.AddConsole().SetMinimumLevel(LogLevel.Information);
            });
            ILogger logger = loggerFactory.CreateLogger<Program>();

            // gRPC 채널 및 클라이언트 생성
            using var channel = GrpcChannel.ForAddress(grpcServer);
            var client = new TdmsService.TdmsService.TdmsServiceClient(channel);
            var httpClient = new HttpClient();

            // 작업에 사용할 Workplan/Project ID (예시, 실제 환경에 맞게 수정)
            string workplanId = "test_workplan"; // tdms가 위치한 workplan id
            string proejctId = "67e50763833acdefbde06abd"; // tdms가 위치한 project id
            Console.WriteLine("Connected to gRPC Server...");

            // 1. ISO API 서버에서 tdms_list 조회 (REST GET)
            var response = await httpClient.GetAsync($"{apiServer}/api/projects/{workplanId}/tdms_list?project_id={proejctId}");
            response.EnsureSuccessStatusCode();
            var json = await response.Content.ReadAsStringAsync();

            // 2. tdms_list 배열 파싱
            using var jsonDoc = JsonDocument.Parse(json);
            var tdmsList = jsonDoc.RootElement.GetProperty("tdms_list");

            // 3. 각 TDMS 파일 반복 처리
            foreach (var tdmsElement in tdmsList.EnumerateArray())
            {
                string? tdms = tdmsElement.GetString();
                logger.LogInformation($"Reading TDMS file: {tdms}");

                // gRPC: ReadTdms로 TDMS 파일 내용(신호 chunk) 스트리밍 수신
                using var call = client.ReadTdms(new TdmsReadRequest { TdmsData = tdms });
                var responseStream = call.ResponseStream;

                // 4. 각 chunk별로 inference 전송 및 결과 수신
                while (await responseStream.MoveNext(CancellationToken.None))
                {
                    string receivedData = responseStream.Current.TdmsData;

                    float timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();

                    // gRPC: SendTdms로 chunk 데이터 + 타임스탬프 전송
                    var sendResponse = await client.SendTdmsAsync(new TdmsSendRequest
                    {
                        TdmsData = receivedData,
                        Timer = timestamp
                    });

                    // gRPC: inference 결과 대기 및 수신 (ReceivedData)
                    var inferenceResponse = await client.ReceivedDataAsync(new DataReceivedRequest());
                    var parsed = JsonSerializer.Deserialize<JsonElement>(inferenceResponse.ReceivedData);
                    var formatted =
                        $"File: {parsed.GetProperty("File").GetString()}\n" +
                        $"Product: {parsed.GetProperty("Product").GetString()}\n" +
                        $"Scaled Mean Spindle: {parsed.GetProperty("Scaled Mean Spindle").GetDouble()}\n" +
                        $"Scaled Mean ACC: {parsed.GetProperty("Scaled Mean ACC").GetDouble()}\n" +
                        $"Prediction Probability: {parsed.GetProperty("Prediction Probability").GetDouble()}\n" +
                        $"Predicted Class: {parsed.GetProperty("Predicted Class").GetString()}\n" +
                        $"Spindle Mean: {parsed.GetProperty("Spindle Mean").GetDouble()}\n" +
                        $"ACC Mean: {parsed.GetProperty("ACC Mean").GetDouble()}";

                    logger.LogInformation($"AI Inference:\n{formatted}");

                    await Task.Delay(1000); // (optional) 결과 대기 시간 조절
                }
            }
        }
    }
}
